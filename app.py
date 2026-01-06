import streamlit as st
import googlemaps
import folium
from streamlit_folium import folium_static
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="Tournée Pro Suisse", layout="wide", initial_sidebar_state="collapsed")

# --- CSS PERSONNALISÉ (Mobile & Design) ---
st.markdown("""
    <style>
    body { font-size: 14px; }
    .stButton>button { width: 100%; border-radius: 8px; }
    .status-ok { color: #28a745; font-weight: bold; }
    .summary-card { 
        background: #f8f9fa; border-radius: 10px; padding: 10px; 
        margin-bottom: 10px; border-left: 5px solid #1f77b4;
    }
    .edit-btn { font-size: 0.8em; color: #1f77b4; cursor: pointer; }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISATION ---
if 'stops' not in st.session_state:
    st.session_state.stops = []
if 'step' not in st.session_state:
    st.session_state.step = 1
if 'edit_idx' not in st.session_state:
    st.session_state.edit_idx = None

# Connexion Google Maps
try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except:
    st.error("Clé API manquante dans les secrets.")
    st.stop()

# --- LOGIQUE DE VALIDATION D'ADRESSE ---
def validate_address(n, r, npa, v):
    query = f"{n} {r} {npa} {v}, Suisse".strip()
    res = gmaps.geocode(query)
    if res:
        addr_comp = res[0]['address_components']
        # Extraction intelligente pour compléter les champs vides
        found_npa = next((c['short_name'] for c in addr_comp if 'postal_code' in c['types']), npa)
        found_ville = next((c['long_name'] for c in addr_comp if 'locality' in c['types']), v)
        return {
            "full": res[0]['formatted_address'],
            "lat": res[0]['geometry']['location']['lat'],
            "lng": res[0]['geometry']['location']['lng'],
            "npa": found_npa,
            "ville": found_ville,
            "raw": {"n":n, "r":r, "npa":npa, "v":v}
        }
    return None

# --- UI : RÉSUMÉ EN BAS DE PAGE ---
def render_summary():
    if st.session_state.stops:
        st.write("---")
        st.subheader("📍 Étapes de la tournée")
        for i, stop in enumerate(st.session_state.stops):
            col1, col2, col3 = st.columns([0.1, 0.7, 0.2])
            with col1:
                st.write(f"**{i+1}**")
            with col2:
                label = "🏠 DÉPÔT" if i == 0 else f"👤 Client {i}"
                st.markdown(f"**{label}** : {stop['full']} <span class='status-ok'>✅</span>", unsafe_allow_html=True)
                if 'time_window' in stop:
                    st.caption(f"Fenêtre: {stop['time_window'][0]} - {stop['time_window'][1]} | {stop['duration']}min")
            with col3:
                if st.button("Modifier", key=f"edit_{i}"):
                    st.session_state.edit_idx = i
                    st.rerun()
        
        # Carte dynamique
        m = folium.Map(location=[st.session_state.stops[0]['lat'], st.session_state.stops[0]['lng']], zoom_start=10)
        for i, s in enumerate(st.session_state.stops):
            folium.Marker([s['lat'], s['lng']], popup=s['full'], tooltip=f"Étape {i+1}").add_to(m)
        folium_static(m, width=700)

# --- WORKFLOW ---

# ETAPE 1 : VEHICULE
if st.session_state.step == 1:
    st.title("1. Catégorie de véhicule")
    v_type = st.radio("Type de transport", ["Voiture", "Poids Lourd"])
    if st.button("Continuer"):
        st.session_state.vehicule = v_type
        st.session_state.step = 2
        st.rerun()

# ETAPE 2 : DEPÔT ET CLIENTS
elif st.session_state.step == 2:
    is_editing = st.session_state.edit_idx is not None
    idx = st.session_state.edit_idx
    
    title = "🏠 Modifier Dépôt" if idx == 0 else ("👤 Modifier Client" if is_editing else "➕ Ajouter un Client")
    st.title(title)
    
    # Pré-remplissage si édition
    prev = st.session_state.stops[idx]['raw'] if is_editing else {"n":"","r":"","npa":"","v":""}
    
    with st.container():
        c1, c2, c3, c4 = st.columns([1,3,1,2])
        num = c1.text_input("N°", prev['n'])
        rue = c2.text_input("Rue", prev['r'])
        npa = c3.text_input("NPA", prev['npa'])
        vil = c4.text_input("Ville", prev['v'])
        
        if idx == 0 or (not is_editing and len(st.session_state.stops) == 0):
            st.session_state.dep_time = st.time_input("Heure de départ du dépôt", datetime.now().replace(hour=8, minute=0))
        else:
            col_t1, col_t2, col_dur = st.columns(3)
            t1 = col_t1.time_input("Début fenêtre", datetime.now().replace(hour=8, minute=0))
            t2 = col_t2.time_input("Fin fenêtre", datetime.now().replace(hour=18, minute=0))
            dur = col_dur.number_input("Temps sur place (min)", 15)

    col_btn1, col_btn2 = st.columns(2)
    
    if col_btn1.button("✅ Valider l'adresse"):
        data = validate_address(num, rue, npa, vil)
        if data:
            if not is_editing:
                if idx == 0: data["type"] = "Dépôt"
                else: 
                    data["type"] = "Client"
                    data["time_window"] = (t1, t2)
                    data["duration"] = dur
                st.session_state.stops.append(data)
            else:
                # Mise à jour
                st.session_state.stops[idx].update(data)
                st.session_state.edit_idx = None
            st.success("Adresse validée et ajoutée !")
            st.rerun()
        else:
            st.error("⚠️ Adresse introuvable. Vérifiez les champs.")

    if len(st.session_state.stops) > 1:
        if st.button("🚀 OPTIMISER LA TOURNÉE"):
            st.session_state.step = 3
            st.rerun()

    render_summary()

# ETAPE 3 : RÉSULTATS
elif st.session_state.step == 3:
    st.title("🏁 Votre Feuille de Route")
    
    # Logique de calcul simplifiée (Itinéraire direct entre points saisis)
    current_time = datetime.combine(datetime.today(), st.session_state.dep_time)
    v_factor = 0.8 if st.session_state.vehicule == "Poids Lourd" else 1.0
    
    for i in range(len(st.session_state.stops) - 1):
        s1 = st.session_state.stops[i]
        s2 = st.session_state.stops[i+1]
        
        # Affichage du point actuel
        st.markdown(f"<div class='summary-card'>📍 **{s1['full']}**</div>", unsafe_allow_html=True)
        
        # Calcul vers le prochain
        res = gmaps.directions(s1['full'], s2['full'], mode="driving")
        if res:
            leg = res[0]['legs'][0]
            dur_min = (leg['duration']['value'] / 60) / v_factor
            
            # Ligne de latence (Vert si > 15min de battement ou simple trajet)
            st.markdown(f"<div style='border-left: 3px solid #28a745; margin-left: 20px; padding: 10px;'>🚚 Trajet : {int(dur_min)} min ({leg['distance']['text']})</div>", unsafe_allow_html=True)
            
            arrival = current_time + timedelta(minutes=dur_min)
            current_time = arrival + timedelta(minutes=s2.get('duration', 0))
            
            if i == len(st.session_state.stops) - 2:
                st.markdown(f"<div class='summary-card'>🏁 **ARRIVÉE : {s2['full']}**<br>🕒 Heure estimée : {arrival.strftime('%H:%M')}</div>", unsafe_allow_html=True)

    if st.button("⬅️ Modifier la liste"):
        st.session_state.step = 2
        st.rerun()
