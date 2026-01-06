import streamlit as st
import googlemaps
from streamlit_folium import folium_static
import folium
from datetime import datetime, timedelta
import polyline

# --- CONFIGURATION & STYLE ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

st.markdown("""
    <style>
    /* Bulle bleue client */
    .client-card {
        background-color: #0047AB;
        color: white;
        padding: 15px;
        border-radius: 10px 10px 0 0;
        margin-top: 10px;
    }
    /* Bloc adresse intégré sous la bulle */
    .address-box {
        background-color: #0047AB;
        padding: 0 15px 10px 15px;
        border-radius: 0 0 10px 10px;
        margin-bottom: 10px;
    }
    /* Style du bouton copier (st.code) pour qu'il soit bleu */
    .address-box code {
        color: white !important;
        background-color: rgba(255,255,255,0.2) !important;
        border: none !important;
    }
    .stButton>button[kind="secondary"] { color: #ff4b4b; border-color: #ff4b4b; }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISATION ---
if 'stops' not in st.session_state: st.session_state.stops = []
if 'step' not in st.session_state: st.session_state.step = 1
if 'vehicle' not in st.session_state: st.session_state.vehicle = "Voiture"
if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None

def reset_form_fields():
    st.session_state.f_nom = ""
    st.session_state.f_num = ""
    st.session_state.f_rue = ""
    st.session_state.f_npa = ""
    st.session_state.f_vil = ""
    st.session_state.f_dur = 15
    st.session_state.f_use_h = False
    st.session_state.f_t1 = datetime.strptime("08:00", "%H:%M").time()
    st.session_state.f_t2 = datetime.strptime("18:00", "%H:%M").time()
    st.session_state.f_hdep = datetime.strptime("08:00", "%H:%M").time()
    st.session_state.edit_idx = None

# Création des clés si inexistantes
if 'f_nom' not in st.session_state:
    reset_form_fields()

try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except:
    st.error("⚠️ Clé API Google manquante dans les secrets.")
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
    col_form, col_map = st.columns([1, 1.2])

    with col_form:
        idx = st.session_state.edit_idx
        is_edit = idx is not None
        # On est au dépôt si (pas d'édition et liste vide) OU (édition de l'index 0)
        is_depot = (not is_edit and len(st.session_state.stops) == 0) or (is_edit and idx == 0)

        st.subheader("🏠 Adresse du Dépôt" if is_depot else "👤 Infos Client")
        
        st.session_state.f_nom = st.text_input("Nom / Enseigne", value=st.session_state.f_nom)
        c1, c2 = st.columns([1, 3])
        st.session_state.f_num = c1.text_input("N°", value=st.session_state.f_num)
        st.session_state.f_rue = c2.text_input("Rue", value=st.session_state.f_rue)
        c3, c4 = st.columns(2)
        st.session_state.f_npa = c3.text_input("NPA", value=st.session_state.f_npa)
        st.session_state.f_vil = c4.text_input("Ville", value=st.session_state.f_vil)
        
        if is_depot:
            st.session_state.f_hdep = st.time_input("Heure de départ de la tournée", value=st.session_state.f_hdep)
        else:
            st.session_state.f_dur = st.number_input("Temps sur place (min)", 5, 120, value=st.session_state.f_dur)
            st.session_state.f_use_h = st.checkbox("Horaire impératif", value=st.session_state.f_use_h)
            if st.session_state.f_use_h:
                ca, cb = st.columns(2)
                st.session_state.f_t1 = ca.time_input("Pas avant", value=st.session_state.f_t1)
                st.session_state.f_t2 = cb.time_input("Pas après", value=st.session_state.f_t2)

        if st.button("✅ Enregistrer l'adresse", type="primary"):
            res = validate_address(st.session_state.f_num, st.session_state.f_rue, st.session_state.f_npa, st.session_state.f_vil)
            if res:
                res["nom"] = "DÉPÔT" if is_depot else (st.session_state.f_nom if st.session_state.f_nom else "Client sans nom")
                if is_depot: 
                    res["h_dep"] = st.session_state.f_hdep
                else: 
                    res.update({"use_h": st.session_state.f_use_h, "dur": st.session_state.f_dur, "t1": st.session_state.f_t1, "t2": st.session_state.f_t2})
                
                if is_edit: st.session_state.stops[idx] = res
                else: st.session_state.stops.append(res)
                
                reset_form_fields()
                st.rerun()
            else:
                st.error(f"❌ ADRESSE NON TROUVÉE : '{st.session_state.f_num} {st.session_state.f_rue}, {st.session_state.f_vil}'. Veuillez vérifier l'orthographe ou le NPA.")

        # Bouton Optimiser placé AU DESSUS du résumé
        if len(st.session_state.stops) > 1:
            st.write("---")
            if st.button("🚀 OPTIMISER LA TOURNÉE", use_container_width=True, type="primary"):
                st.session_state.step = 3
                st.rerun()

        st.subheader("📋 Liste des arrêts")
        for i, s in enumerate(st.session_state.stops):
            c_t, c_e, c_d = st.columns([3, 0.5, 0.5])
            prefix = "🏠" if i == 0 else f"{i}."
            c_t.write(f"**{prefix} {s['nom']}**")
            if c_e.button("✏️", key=f"ed_{i}"):
                st.session_state.edit_idx = i
                st.session_state.f_nom = s['nom']
                st.session_state.f_num = s['raw']['n']
                st.session_state.f_rue = s['raw']['r']
                st.session_state.f_npa = s['raw']['npa']
                st.session_state.f_vil = s['raw']['v']
                if i == 0: st.session_state.f_hdep = s['h_dep']
                else:
                    st.session_state.f_dur = s['dur']
                    st.session_state.f_use_h = s['use_h']
                    st.session_state.f_t1, st.session_state.f_t2 = s['t1'], s['t2']
                st.rerun()
            if c_d.button("🗑️", key=f"dl_{i}"):
                st.session_state.stops.pop(i)
                st.rerun()

    with col_map:
        m = folium.Map(location=[46.8, 8.2], zoom_start=7)
        for i, s in enumerate(st.session_state.stops):
            folium.Marker([s['lat'], s['lng']], tooltip=s['nom'], icon=folium.Icon(color="red" if i==0 else "blue")).add_to(m)
        folium_static(m, width=500)

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
        
        m_final = folium.Map(location=[st.session_state.stops[0]['lat'], st.session_state.stops[0]['lng']], zoom_start=10)
        
        # Affichage du Dépôt (Départ)
        st.info(f"🏠 **DÉPART DU DÉPÔT : {current_time.strftime('%H:%M')}**")

        for i, leg in enumerate(legs[:-1]):
            dur_mins = int((leg['duration']['value'] / 60) * t_mult)
            st.markdown(f'<div style="border: 2px solid #FF8C00; border-radius: 10px; padding: 5px; text-align: center; margin: 10px 0; color: #FF8C00; font-weight: bold;">⏱️ Trajet : {leg["distance"]["text"]} ({dur_mins} min)</div>', unsafe_allow_html=True)
            
            arrival_time = current_time + timedelta(minutes=dur_mins)
            client = st.session_state.stops[order[i] + 1]
            
            if client['use_h'] and arrival_time < datetime.combine(datetime.today(), client['t1']):
                arrival_time = datetime.combine(datetime.today(), client['t1'])

            # BULLE BLEUE + ADRESSE COPIABLE
            st.markdown(f"""
                <div class="client-card">
                    <h3 style="margin:0; color: white;">{i+1}. {client['nom']}</h3>
                    <p style="margin: 5px 0; opacity: 0.9;">⌚ Arrivée : <b>{arrival_time.strftime('%H:%M')}</b> | 📦 Temps sur place : {client['dur']} min</p>
                </div>
            """, unsafe_allow_html=True)
            st.markdown('<div class="address-box">', unsafe_allow_html=True)
            st.code(client['full'], language=None)
            st.markdown('</div>', unsafe_allow_html=True)

            folium.Marker([client['lat'], client['lng']], popup=client['nom'], icon=folium.Icon(color="blue", icon="info-sign")).add_to(m_final)
            current_time = arrival_time + timedelta(minutes=client['dur'])

        # Tracé de la route sur la carte
        poly = res[0]['overview_polyline']['points']
        folium.PolyLine(polyline.decode(poly), color="blue", weight=5, opacity=0.7).add_to(m_final)

        st.subheader("🗺️ Carte de la tournée")
        folium_static(m_final, width=1000)

        if st.button("⬅️ Retour"):
            st.session_state.step = 2
            st.rerun()
