import streamlit as st
import googlemaps
from streamlit_folium import folium_static
import folium
from datetime import datetime, timedelta
import polyline

# --- CONFIGURATION ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

# CSS pour supprimer les blocs gris et styliser les champs de copie
st.markdown("""
    <style>
    /* Stylisation du champ d'adresse pour qu'il soit invisible (fond bleu) */
    .stTextInput input {
        background-color: rgba(255, 255, 255, 0.1) !important;
        color: white !important;
        border: 1px dashed rgba(255, 255, 255, 0.5) !important;
        cursor: pointer;
    }
    div[data-baseweb="input"] { background-color: transparent !important; }
    </style>
    """, unsafe_allow_html=True)

if 'stops' not in st.session_state: st.session_state.stops = []
if 'step' not in st.session_state: st.session_state.step = 1
if 'vehicle' not in st.session_state: st.session_state.vehicle = "Voiture"
if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None

# Initialisation des clés de formulaire pour la réinitialisation sélective
for key in ['f_nom', 'f_num', 'f_rue', 'f_npa', 'f_vil']:
    if key not in st.session_state: st.session_state[key] = ""

try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except:
    st.error("Clé API Google manquante.")
    st.stop()

def validate_address(n, r, npa, v):
    query = f"{n} {r} {npa} {v}, Suisse".strip()
    res = gmaps.geocode(query)
    if res:
        c = res[0]['address_components']
        f_npa = next((x['short_name'] for x in c if 'postal_code' in x['types']), npa)
        f_vil = next((x['long_name'] for x in c if 'locality' in x['types']), v)
        return {
            "full": res[0]['formatted_address'],
            "lat": res[0]['geometry']['location']['lat'],
            "lng": res[0]['geometry']['location']['lng'],
            "raw": {"n":n, "r":r, "npa":npa, "v":v}
        }
    return None

# --- ÉTAPE 1 : VÉHICULE ---
if st.session_state.step == 1:
    st.title("🚚 Catégorie de véhicule")
    v = st.radio("Type de véhicule :", ["Voiture", "Camion (Lourd)"])
    if st.button("Continuer ➡️"):
        st.session_state.vehicle = v
        st.session_state.step = 2
        st.rerun()

# --- ÉTAPE 2 : CONFIGURATION ---
elif st.session_state.step == 2:
    st.title(f"📍 Configuration ({st.session_state.vehicle})")
    col_form, col_map = st.columns([1, 1])

    with col_form:
        idx = st.session_state.edit_idx
        is_edit = idx is not None
        is_depot = (not is_edit and len(st.session_state.stops) == 0) or (is_edit and idx == 0)

        # Pré-remplissage si modification
        if is_edit and not st.session_state.f_nom:
            s = st.session_state.stops[idx]
            st.session_state.f_nom, st.session_state.f_num = s['nom'], s['raw']['n']
            st.session_state.f_rue, st.session_state.f_npa = s['raw']['r'], s['raw']['npa']
            st.session_state.f_vil = s['raw']['v']

        with st.form("form_stop"):
            st.subheader("🏠 Dépôt" if is_depot else "👤 Client")
            nom = st.text_input("Nom", value="Dépôt" if is_depot else st.session_state.f_nom)
            c1, c2 = st.columns([1, 3])
            num = c1.text_input("N°", value=st.session_state.f_num)
            rue = c2.text_input("Rue", value=st.session_state.f_rue)
            c3, c4 = st.columns(2)
            npa = c3.text_input("NPA", value=st.session_state.f_npa)
            vil = c4.text_input("Ville", value=st.session_state.f_vil)
            
            if is_depot:
                h_dep = st.time_input("Heure de départ", datetime.now().replace(hour=8, minute=0))
            else:
                ca, cb = st.columns(2)
                use_h = ca.checkbox("Horaire impératif")
                dur = cb.number_input("Temps sur place (min)", 5, 60, 15)
                t1 = st.time_input("Pas avant", datetime.now().replace(hour=8, minute=0))
                t2 = st.time_input("Pas après", datetime.now().replace(hour=18, minute=0))

            if st.form_submit_button("Valider l'adresse"):
                res = validate_address(num, rue, npa, vil)
                if res:
                    # SUCCÈS : On enregistre et on vide les champs
                    res["nom"] = "Dépôt" if is_depot else nom
                    if is_depot: res["h_dep"] = h_dep
                    else: res.update({"use_h":use_h, "dur":dur, "t1":t1, "t2":t2})
                    
                    if is_edit: st.session_state.stops[idx] = res
                    else: st.session_state.stops.append(res)
                    
                    # Réinitialisation des champs pour le prochain
                    for k in ['f_nom', 'f_num', 'f_rue', 'f_npa', 'f_vil']: st.session_state[k] = ""
                    st.session_state.edit_idx = None
                    st.rerun()
                else:
                    # ÉCHEC : On garde les infos dans les champs
                    st.session_state.f_nom, st.session_state.f_num = nom, num
                    st.session_state.f_rue, st.session_state.f_npa = rue, npa
                    st.session_state.f_vil = vil
                    st.error("Adresse introuvable. Modifiez les champs.")

        # Liste résumé
        for i, s in enumerate(st.session_state.stops):
            if st.button(f"✏️ {i}. {s['nom']} - {s['full']}", key=f"btn_{i}"):
                st.session_state.edit_idx = i
                st.rerun()

    with col_map:
        m = folium.Map(location=[46.8, 8.2], zoom_start=7)
        for s in st.session_state.stops:
            folium.Marker([s['lat'], s['lng']], tooltip=s['nom']).add_to(m)
        folium_static(m, width=600)

    if len(st.session_state.stops) > 1:
        if st.button("🚀 OPTIMISER LA TOURNÉE", use_container_width=True):
            st.session_state.step = 3
            st.rerun()

# --- ÉTAPE 3 : FEUILLE DE ROUTE ---
elif st.session_state.step == 3:
    st.title("🏁 Feuille de Route Optimisée")
    t_mult = 1.25 if st.session_state.vehicle == "Camion (Lourd)" else 1.0
    
    origin = st.session_state.stops[0]['full']
    destinations = [s['full'] for s in st.session_state.stops[1:]]
    res = gmaps.directions(origin, origin, waypoints=destinations, optimize_waypoints=True)
    
    if res:
        order = res[0]['waypoint_order']
        legs = res[0]['legs']
        current_time = datetime.combine(datetime.today(), st.session_state.stops[0]['h_dep'])
        
        st.info(f"🚚 Véhicule : **{st.session_state.vehicle}** | 🕒 Départ : **{current_time.strftime('%H:%M')}**")
        
        for i, leg in enumerate(legs[:-1]):
            dist_km = leg['distance']['text']
            # Temps Google ajusté par le type de véhicule
            dur_mins = int((leg['duration']['value'] / 60) * t_mult)
            
            # CADRE ORANGE POUR LE TRAJET
            st.markdown(f"""
                <div style="border: 2px solid #FF8C00; border-radius: 10px; padding: 10px; text-align: center; margin: 20px 0; color: #FF8C00; font-weight: bold;">
                ⏱️ Trajet : {dist_km} — Env. {dur_mins} mins
                </div>
            """, unsafe_allow_html=True)
            
            arrival_time = current_time + timedelta(minutes=dur_mins)
            client = st.session_state.stops[order[i] + 1]
            
            # BULLE BLEUE UNIQUE
            st.markdown(f"""
                <div style="background-color: #0047AB; color: white; padding: 15px; border-radius: 10px 10px 0 0; border: 1px solid #0047AB; border-bottom: none;">
                    <h3 style="margin:0; color: white;">{i+1}. {client['nom']}</h3>
                    <p style="margin: 5px 0; font-size: 14px;">
                        ⌚ Arrivée : <b>{arrival_time.strftime('%H:%M')}</b> | 📦 Sur place : {client['dur']} min
                    </p>
                </div>
            """, unsafe_allow_html=True)
            
            # ADRESSE DANS LE BLOC BLEU (Champ cliquable pour copie)
            with st.container():
                st.markdown('<div style="background-color: #0047AB; padding: 0 15px 15px 15px; border-radius: 0 0 10px 10px; border: 1px solid #0047AB; border-top: none;">', unsafe_allow_html=True)
                st.text_input("Copier l'adresse :", value=client['full'], key=f"copy_{i}", label_visibility="collapsed")
                st.markdown('</div>', unsafe_allow_html=True)

            current_time = arrival_time + timedelta(minutes=client['dur'])

    if st.button("⬅️ Retour"):
        st.session_state.step = 2
        st.rerun()
