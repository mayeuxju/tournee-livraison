import streamlit as st
import googlemaps
import pandas as pd
import folium
from streamlit_folium import folium_static
from datetime import datetime, timedelta
import plotly.express as px

# --- CONFIGURATION ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

# --- STYLE CSS ---
st.markdown("""
    <style>
    .latency-line {
        border-left: 4px solid #28a745;
        margin: 0px 0px 0px 35px;
        padding: 10px 0px 10px 25px;
        color: #28a745; font-weight: bold; font-size: 0.9em;
    }
    .stop-card {
        background: white; padding: 15px; border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05); border-left: 5px solid #1f77b4;
        margin-bottom: 5px;
    }
    .stButton>button { width: 100%; }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISATION SESSION STATE ---
if 'stops' not in st.session_state:
    st.session_state.stops = [] # Liste des adresses
if 'step' not in st.session_state:
    st.session_state.step = 1

# API Google
try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except:
    st.error("Configurez votre clé API Google dans les Secrets.")
    st.stop()

# --- FONCTIONS UTILES ---
def format_address(n, r, npa, v):
    """Combine les champs pour Google Maps"""
    parts = [n, r, npa, v]
    return " ".join([str(p) for p in parts if p]).strip()

def get_lat_lng(addr):
    """Vérifie si l'adresse existe et renvoie les coordonnées"""
    res = gmaps.geocode(addr)
    if res:
        return res[0]['geometry']['location'], res[0]['formatted_address']
    return None, None

# --- WORKFLOW PAR ÉTAPES ---

# ÉTAPE 1 : VÉHICULE
if st.session_state.step == 1:
    st.title("Step 1 : Catégorie de véhicule")
    vehicule = st.selectbox("Choisissez votre véhicule", ["Voiture / Utilitaire léger", "Poids Lourd (Vitesse réduite)"])
    st.session_state.vehicule_type = vehicule
    if st.button("Suivant ➡️"):
        st.session_state.step = 2
        st.rerun()

# ÉTAPE 2 : DÉPÔT (DÉPART)
elif st.session_state.step == 2:
    st.title("Step 2 : Point de départ (Dépôt)")
    col1, col2, col3, col4 = st.columns([1,3,1,2])
    n = col1.text_input("N°")
    r = col2.text_input("Rue")
    npa = col3.text_input("NPA")
    v = col4.text_input("Ville")
    
    dep_time = st.time_input("Heure de départ du dépôt", datetime.now().replace(hour=8, minute=0))
    
    if st.button("Valider le dépôt ➡️"):
        full_addr = format_address(n, r, npa, v)
        loc, clean_addr = get_lat_lng(full_addr)
        if loc:
            st.session_state.stops = [{
                "type": "Dépôt",
                "address": clean_addr,
                "lat": loc['lat'], "lng": loc['lng'],
                "time_window": (dep_time, dep_time),
                "duration": 0
            }]
            st.session_state.step = 3
            st.rerun()
        else:
            st.error("Adresse introuvable. Modifiez vos champs.")

# ÉTAPE 3 : AJOUT DES CLIENTS
elif st.session_state.step == 3:
    st.title("Step 3 : Liste des clients")
    
    with st.expander("➕ Ajouter un client", expanded=True):
        c1, c2, c3, c4 = st.columns([1,3,1,2])
        cn = c1.text_input("N°", key="cn")
        cr = c2.text_input("Rue", key="cr")
        cnpa = c3.text_input("NPA", key="cnpa")
        cv = c4.text_input("Ville", key="cv")
        
        col_t1, col_t2, col_dur = st.columns(3)
        t_start = col_t1.time_input("Début fenêtre", datetime.now().replace(hour=9, minute=0))
        t_end = col_t2.time_input("Fin fenêtre", datetime.now().replace(hour=18, minute=0))
        dur = col_dur.number_input("Temps sur place (min)", value=15)
        
        if st.button("Ajouter à la tournée"):
            addr = format_address(cn, cr, cnpa, cv)
            loc, clean_addr = get_lat_lng(addr)
            if loc:
                st.session_state.stops.append({
                    "type": "Client",
                    "address": clean_addr,
                    "lat": loc['lat'], "lng": loc['lng'],
                    "time_window": (t_start, t_end),
                    "duration": dur,
                    "raw": {"n":cn, "r":cr, "npa":cnpa, "v":cv} # Sauvegarde pour modif
                })
                st.success(f"Ajouté : {clean_addr}")
            else:
                st.error("Adresse non reconnue. Corrigez les champs ci-dessus.")

    # Affichage de la liste actuelle
    st.subheader(f"Ma tournée ({len(st.session_state.stops)-1} clients)")
    for i, s in enumerate(st.session_state.stops):
        if i == 0: continue
        col_list, col_del = st.columns([0.9, 0.1])
        col_list.info(f"**{i}.** {s['address']} | 🕒 {s['time_window'][0]} - {s['time_window'][1]}")
        if col_del.button("❌", key=f"del_{i}"):
            st.session_state.stops.pop(i)
            st.rerun()

    if len(st.session_state.stops) > 1:
        if st.button("🏁 OPTIMISER ET GÉNÉRER LA TOURNÉE"):
            st.session_state.step = 4
            st.rerun()

# ÉTAPE 4 : RÉSULTATS
elif st.session_state.step == 4:
    st.title("📊 Feuille de Route Optimisée")
    
    # Calcul des trajets (simplifié pour l'exemple, peut être étendu avec OR-Tools)
    itinerary = []
    current_time = datetime.combine(datetime.today(), st.session_state.stops[0]['time_window'][0])
    
    v_factor = 0.8 if st.session_state.vehicule_type == "Poids Lourd" else 1.0
    
    for i in range(len(st.session_state.stops) - 1):
        origin = st.session_state.stops[i]
        dest = st.session_state.stops[i+1]
        
        res = gmaps.directions(origin['address'], dest['address'], mode="driving", departure_time=datetime.now())
        
        if res:
            leg = res[0]['legs'][0]
            dur_sec = (leg['duration']['value'] / v_factor)
            dist_txt = leg['distance']['text']
            
            # Temps de trajet
            travel_time = timedelta(seconds=int(dur_sec))
            arrival_time = current_time + travel_time
            
            itinerary.append({
                "from": origin['address'],
                "to": dest['address'],
                "dist": dist_txt,
                "dur": str(travel_time),
                "arrival": arrival_time.strftime("%H:%M")
            })
            # Temps passé chez le client
            current_time = arrival_time + timedelta(minutes=dest['duration'])

    # AFFICHAGE
    tab1, tab2 = st.tabs(["📝 Itinéraire", "🗺️ Carte"])
    
    with tab1:
        st.markdown(f'<div class="stop-card">🏠 **DÉPART DÉPÔT** : {st.session_state.stops[0]["address"]} <br> 🕒 Départ à {st.session_state.stops[0]["time_window"][0]}</div>', unsafe_allow_html=True)
        
        for item in itinerary:
            st.markdown(f'<div class="latency-line">🚚 Trajet : {item["dur"]} ({item["dist"]})</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="stop-card">📍 **ARRIVÉE** : {item["to"]} <br> 🕒 Heure estimée : **{item["arrival"]}**</div>', unsafe_allow_html=True)

    with tab2:
        m = folium.Map(location=[st.session_state.stops[0]['lat'], st.session_state.stops[0]['lng']], zoom_start=12)
        for s in st.session_state.stops:
            folium.Marker([s['lat'], s['lng']], popup=s['address']).add_to(m)
        folium_static(m)

    if st.button("🔄 Recommencer / Modifier"):
        st.session_state.step = 3
        st.rerun()
