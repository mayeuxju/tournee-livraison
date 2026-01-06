import streamlit as st
import googlemaps
from streamlit_folium import folium_static
import folium
from datetime import datetime, timedelta

# --- CONFIGURATION & STYLE ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

st.markdown("""
    <style>
    /* Intégration transparente du champ de copie dans la bulle bleue */
    .blue-bubble-address input {
        background-color: rgba(255, 255, 255, 0.2) !important;
        color: white !important;
        border: 1px solid rgba(255, 255, 255, 0.4) !important;
        border-radius: 5px !important;
        cursor: pointer;
    }
    .blue-bubble-address div[data-baseweb="input"] {
        background-color: transparent !important;
    }
    /* Style bouton supprimer */
    .stButton>button[kind="secondary"] {
        color: #ff4b4b;
        border-color: #ff4b4b;
    }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISATION ---
if 'stops' not in st.session_state: st.session_state.stops = []
if 'step' not in st.session_state: st.session_state.step = 1
if 'vehicle' not in st.session_state: st.session_state.vehicle = "Voiture"
if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None

# Variables de formulaire persistantes
for key in ['f_nom', 'f_num', 'f_rue', 'f_npa', 'f_vil']:
    if key not in st.session_state: st.session_state[key] = ""

try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except:
    st.error("⚠️ Clé API Google manquante.")
    st.stop()

def validate_address(n, r, npa, v):
    query = f"{n} {r} {npa} {v}, Suisse".strip()
    res = gmaps.geocode(query)
    if res:
        return {
            "full": res[0]['formatted_address'],
            "lat": res[0]['geometry']['location']['lat'],
            "lng": res[0]['geometry']['location']['lng'],
            "raw": {"n":n, "r":r, "npa":npa, "v":v}
        }
    return None

# --- ÉTAPE 1 : VÉHICULE ---
if st.session_state.step == 1:
    st.title("🚚 Type de transport")
    v = st.radio("Sélectionnez votre véhicule :", ["Voiture", "Camion (Lourd)"])
    if st.button("Valider et continuer ➡️"):
        st.session_state.vehicle = v
        st.session_state.step = 2
        st.rerun()

# --- ÉTAPE 2 : CONFIGURATION TOURNÉE ---
elif st.session_state.step == 2:
    st.title(f"📍 Configuration ({st.session_state.vehicle})")
    col_form, col_map = st.columns([1, 1])

    with col_form:
        idx = st.session_state.edit_idx
        is_edit = idx is not None
        is_depot = (not is_edit and len(st.session_state.stops) == 0) or (is_edit and idx == 0)

        # Remplissage si mode modification
        if is_edit and not st.session_state.f_nom:
            s = st.session_state.stops[idx]
            st.session_state.f_nom, st.session_state.f_num = s['nom'], s['raw']['n']
            st.session_state.f_rue, st.session_state.f_npa = s['raw']['r'], s['raw']['npa']
            st.session_state.f_vil = s['raw']['v']

        with st.form("form_stop"):
            st.subheader("🏠 Dépôt" if is_depot else "👤 Client")
            nom = st.text_input("Nom / Enseigne", value="Dépôt" if is_depot else st.session_state.f_nom)
            c1, c2 = st.columns([1, 3])
            num = c1.text_input("N°", value=st.session_state.f_num)
            rue = c2.text_input("Rue", value=st.session_state.f_rue)
            c3, c4 = st.columns(2)
            npa = c3.text_input("NPA", value=st.session_state.f_npa)
            vil = c4.text_input("Ville", value=st.session_state.f_vil)
            
            if is_depot:
                h_dep = st.time_input("Heure de départ", datetime.now().replace(hour=8, minute=0))
            else:
                dur = st.number_input("Temps sur place (min)", 5, 120, 15)
                use_h = st.checkbox("Horaire impératif", value=st.session_state.get('last_use_h', False))
                if use_h:
                    ca, cb = st.columns(2)
                    t1 = ca.time_input("Pas avant", datetime.now().replace(hour=8, minute=0))
                    t2 = cb.time_input("Pas après", datetime.now().replace(hour=18, minute=0))
                else:
                    t1, t2 = None, None

            if st.form_submit_button("✅ Enregistrer"):
                res = validate_address(num, rue, npa, vil)
                if res:
                    res["nom"] = "Dépôt" if is_depot else nom
                    if is_depot: res["h_dep"] = h_dep
                    else: res.update({"use_h":use_h, "dur":dur, "t1":t1, "t2":t2})
                    
                    if is_edit: st.session_state.stops[idx] = res
                    else: st.session_state.stops.append(res)
                    
                    for k in ['f_nom', 'f_num', 'f_rue', 'f_npa', 'f_vil']: st.session_state[k] = ""
                    st.session_state.edit_idx = None
                    st.rerun()
                else:
                    st.session_state.f_nom, st.session_state.f_num = nom, num
                    st.session_state.f_rue, st.session_state.f_npa = rue, npa
                    st.session_state.f_vil = vil
                    st.error(f"⚠️ L'adresse '{num} {rue}, {npa} {vil}' n'a pas été trouvée.")

        # --- RÉSUMÉ ET OPTIMISATION ---
        if len(st.session_state.stops) > 1:
            st.write("---")
            if st.button("🚀 OPTIMISER LA TOURNÉE", use_container_width=True, type="primary"):
                st.session_state.step = 3
                st.rerun()

        st.subheader("📋 Résumé de la tournée")
        for i, s in enumerate(st.session_state.stops):
            col_txt, col_edit, col_del = st.columns([3, 0.5, 0.5])
            col_txt.write(f"**{i}. {s['nom']}**  \n{s['full']}")
            
            if col_edit.button("✏️", key=f"edit_{i}"):
                st.session_state.edit_idx = i
                st.rerun()
            
            if col_del.button("🗑️", key=f"del_{i}"):
                st.session_state.stops.pop(i)
                st.rerun()

    with col_map:
        m = folium.Map(location=[46.8, 8.2], zoom_start=7)
        for i, s in enumerate(st.session_state.stops):
            folium.Marker([s['lat'], s['lng']], tooltip=s['nom'], 
                          icon=folium.Icon(color="red" if i==0 else "blue")).add_to(m)
        folium_static(m, width=600)

# --- ÉTAPE 3 : FEUILLE DE ROUTE OPTIMISÉE ---
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
        
        st.success(f"🚚 **{st.session_state.vehicle}** | Départ : **{current_time.strftime('%H:%M')}**")
        
        for i, leg in enumerate(legs[:-1]):
            dist_km, dur_mins = leg['distance']['text'], int((leg['duration']['value'] / 60) * t_mult)
            
            # CADRE ORANGE
            st.markdown(f'<div style="border: 2px solid #FF8C00; border-radius: 10px; padding: 8px; text-align: center; margin: 15px 0; color: #FF8C00; font-weight: bold;">⏱️ Trajet : {dist_km} — Env. {dur_mins} mins</div>', unsafe_allow_html=True)
            
            arrival_time = current_time + timedelta(minutes=dur_mins)
            client = st.session_state.stops[order[i] + 1]
            
            if client['use_h'] and arrival_time < datetime.combine(datetime.today(), client['t1']):
                arrival_time = datetime.combine(datetime.today(), client['t1'])

            # BULLE BLEUE UNIFIÉE
            st.markdown(f"""
                <div style="background-color: #0047AB; color: white; padding: 15px; border-radius: 10px; border: 1px solid #0047AB;">
                    <h3 style="margin:0; color: white; font-size: 18px;">{i+1}. {client['nom']}</h3>
                    <p style="margin: 5px 0; font-size: 14px; opacity: 0.9;">
                        ⌚ Arrivée : <b>{arrival_time.strftime('%H:%M')}</b> | 📦 Sur place : {client['dur']} min
                    </p>
                    <div class="blue-bubble-address">
            """, unsafe_allow_html=True)
            
            # Champ d'adresse à l'intérieur du HTML (via Streamlit pour la fonction copie)
            st.text_input("Copier", value=client['full'], key=f"cp_{i}", label_visibility="collapsed")
            
            st.markdown("</div></div>", unsafe_allow_html=True)
            current_time = arrival_time + timedelta(minutes=client['dur'])

        st.write("---")
        if st.button("⬅️ Retour à la configuration"):
            st.session_state.step = 2
            st.rerun()
