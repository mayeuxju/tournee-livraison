import streamlit as st
import googlemaps
import folium
from streamlit_folium import folium_static
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="Tournée Pro Suisse", layout="wide")

# --- STYLE ---
st.markdown("""
    <style>
    .status-ok { color: #28a745; font-weight: bold; background: #e8f5e9; padding: 2px 8px; border-radius: 4px; }
    .summary-card { 
        background: white; border-radius: 8px; padding: 15px; 
        margin-bottom: 10px; border: 1px solid #ddd; border-left: 6px solid #1f77b4;
    }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISATION ---
if 'stops' not in st.session_state: st.session_state.stops = []
if 'step' not in st.session_state: st.session_state.step = 1
if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None

try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except:
    st.error("Clé API manquante.")
    st.stop()

# --- LOGIQUE ADRESSE ---
def validate_address(n, r, npa, v):
    query = f"{n} {r} {npa} {v}, Suisse".strip()
    res = gmaps.geocode(query)
    if res:
        c = res[0]['address_components']
        # On extrait les infos réelles trouvées par Google pour compléter les trous
        f_npa = next((x['short_name'] for x in c if 'postal_code' in x['types']), npa)
        f_vil = next((x['long_name'] for x in c if 'locality' in x['types']), v)
        return {
            "full": res[0]['formatted_address'],
            "lat": res[0]['geometry']['location']['lat'],
            "lng": res[0]['geometry']['location']['lng'],
            "npa": f_npa, "ville": f_vil, "raw": {"n":n, "r":r, "npa":npa, "v":v}
        }
    return None

# --- UI : RÉSUMÉ & CARTE ---
def render_summary():
    if st.session_state.stops:
        st.write("---")
        st.subheader("📍 Récapitulatif de la tournée")
        for i, stop in enumerate(st.session_state.stops):
            col_icon, col_txt, col_edit = st.columns([0.1, 0.7, 0.2])
            with col_icon: st.write("🏠" if i==0 else f"📍 {i}")
            with col_txt:
                st.markdown(f"**{stop['full']}** <span class='status-ok'>✅ Trouvé</span>", unsafe_allow_html=True)
                if i > 0 and stop.get('use_time'):
                    st.caption(f"Fenêtre : {stop['t1']} - {stop['t2']} | Arrêt : {stop['dur']} min")
            with col_edit:
                if st.button("📝 Modifier", key=f"edit_{i}"):
                    st.session_state.edit_idx = i
                    st.rerun()
        
        m = folium.Map(location=[st.session_state.stops[0]['lat'], st.session_state.stops[0]['lng']], zoom_start=11)
        for i, s in enumerate(st.session_state.stops):
            folium.Marker([s['lat'], s['lng']], popup=s['full'], tooltip=f"Étape {i}").add_to(m)
        folium_static(m)

# --- WORKFLOW ---

# ÉTAPE 1 : CHOIX VÉHICULE
if st.session_state.step == 1:
    st.title("🚚 Configuration du véhicule")
    v_type = st.radio("Type de transport", ["Voiture / Utilitaire", "Poids Lourd (Lent)"])
    if st.button("Continuer ➡️"):
        st.session_state.vehicule = v_type
        st.session_state.step = 2
        st.rerun()

# ÉTAPE 2 : SAISIE (DEPOT + CLIENTS)
elif st.session_state.step == 2:
    idx = st.session_state.edit_idx
    is_editing = idx is not None
    # Est-ce le dépôt ? (Soit liste vide, soit on édite l'index 0)
    is_depot = (not is_editing and len(st.session_state.stops) == 0) or (is_editing and idx == 0)

    st.title("🏠 Dépôt (Départ)" if is_depot else ("📝 Modifier Client" if is_editing else "👤 Ajouter un Client"))
    
    # Valeurs par défaut
    p = st.session_state.stops[idx]['raw'] if is_editing else {"n":"","r":"","npa":"","v":""}
    
    with st.form("add_stop"):
        c1, c2, c3, c4 = st.columns([1,3,1,2])
        num = c1.text_input("N°", p['n'])
        rue = c2.text_input("Rue", p['r'])
        npa = c3.text_input("NPA", p['npa'])
        vil = c4.text_input("Ville", p['v'])
        
        t1, t2, dur, use_time = None, None, 0, False
        if is_depot:
            dep_time = st.time_input("Heure de départ", datetime.now().replace(hour=8, minute=0))
        else:
            st.write("---")
            use_time = st.checkbox("Définir une contrainte horaire ?", value=False)
            col_t1, col_t2, col_dur = st.columns(3)
            t1 = col_t1.time_input("Dès", datetime.now().replace(hour=8, minute=0))
            t2 = col_t2.time_input("Jusqu'à", datetime.now().replace(hour=18, minute=0))
            dur = col_dur.number_input("Temps sur place (min)", 15)

        submitted = st.form_submit_button("✅ Valider l'adresse")
        
        if submitted:
            data = validate_address(num, rue, npa, vil)
            if data:
                data["use_time"] = use_time
                if is_depot:
                    data["dep_time"] = dep_time
                else:
                    data["t1"], data["t2"], data["dur"] = t1, t2, dur
                
                if is_editing:
                    st.session_state.stops[idx] = data
                    st.session_state.edit_idx = None
                else:
                    st.session_state.stops.append(data)
                st.rerun()
            else:
                st.error("Impossible de trouver cette adresse.")

    if len(st.session_state.stops) > 1:
        if st.button("🚀 CALCULER L'ITINÉRAIRE"):
            st.session_state.step = 3
            st.rerun()

    render_summary()

# ÉTAPE 3 : RÉSULTAT
elif st.session_state.step == 3:
    st.title("🏁 Feuille de Route Optimisée")
    # Logique de calcul simple (A vers B vers C...)
    # [Le reste du calcul de l'itinéraire viendrait ici]
    st.write("Calcul en cours...")
    if st.button("⬅️ Retour aux modifications"):
        st.session_state.step = 2
        st.rerun()
