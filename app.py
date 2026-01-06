import streamlit as st
import googlemaps
from datetime import datetime, timedelta

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

# --- INITIALISATION DES VARIABLES ---
if 'stops' not in st.session_state: st.session_state.stops = []
if 'step' not in st.session_state: st.session_state.step = 1  # On commence à l'étape 1
if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None

# Connexion à Google Maps
try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except Exception as e:
    st.error("Erreur de clé API : Vérifiez vos Secrets Streamlit.")
    st.stop()

# --- FONCTION DE VALIDATION D'ADRESSE ---
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
            "npa": f_npa, "ville": f_vil, "raw": {"n":n, "r":r, "npa":npa, "v":v}
        }
    return None

# --- ÉTAPE 1 : ACCUEIL (Pour éviter l'écran noir) ---
if st.session_state.step == 1:
    st.title("🚛 Tournée Pro Suisse")
    st.write("Bienvenue dans votre outil d'optimisation de tournée.")
    st.info("Nous allons commencer par configurer votre point de départ (Dépôt).")
    if st.button("Commencer la configuration ➡️"):
        st.session_state.step = 2
        st.rerun()

# --- ÉTAPE 2 : SAISIE DES ADRESSES ---
elif st.session_state.step == 2:
    idx = st.session_state.edit_idx
    is_editing = idx is not None
    is_depot = (not is_editing and len(st.session_state.stops) == 0) or (is_editing and idx == 0)

    st.title("🏠 Configuration du Dépôt" if is_depot else "👤 Ajouter un Client")
    
    # Valeurs par défaut si on modifie
    p = st.session_state.stops[idx]['raw'] if is_editing else {"n":"","r":"","npa":"","v":""}
    
    with st.form("form_stop"):
        col1, col2, col3, col4 = st.columns([1,3,1,2])
        num = col1.text_input("N°", p['n'])
        rue = col2.text_input("Rue", p['r'])
        npa = col3.text_input("NPA", p['npa'])
        vil = col4.text_input("Ville", p['v'])
        
        if is_depot:
            dep_time = st.time_input("Heure de départ du dépôt", datetime.now().replace(hour=8, minute=0))
        else:
            c_h1, c_h2, c_h3 = st.columns(3)
            use_h = c_h1.checkbox("Horaire impératif ?")
            t1 = c_h2.time_input("Pas avant", datetime.now().replace(hour=8, minute=0))
            t2 = c_h3.time_input("Pas après", datetime.now().replace(hour=18, minute=0))
            dur = st.slider("Durée sur place (min)", 5, 120, 15)

        if st.form_submit_button("✅ Valider l'adresse"):
            result = validate_address(num, rue, npa, vil)
            if result:
                if is_depot: result["dep_time"] = dep_time
                else: result.update({"t1":t1, "t2":t2, "dur":dur, "use_h":use_h})
                
                if is_editing: st.session_state.stops[idx] = result
                else: st.session_state.stops.append(result)
                st.session_state.edit_idx = None
                st.rerun()
            else:
                st.error("Adresse introuvable, vérifiez les champs.")

    # Affichage de la liste actuelle
    if st.session_state.stops:
        st.write("---")
        for i, s in enumerate(st.session_state.stops):
            c1, c2, c3 = st.columns([0.1, 0.7, 0.2])
            c1.write("🏠" if i==0 else f"📍 {i}")
            c2.write(f"**{s['full']}**")
            if c3.button("Modifier", key=f"btn_{i}"):
                st.session_state.edit_idx = i
                st.rerun()

    if len(st.session_state.stops) > 1:
        st.write("---")
        if st.button("🚀 CALCULER L'ITINÉRAIRE OPTIMISÉ", use_container_width=True):
            st.session_state.step = 3
            st.rerun()

# --- ÉTAPE 3 : RÉSULTATS ---
elif st.session_state.step == 3:
    st.title("🏁 Feuille de Route")
    
    origin = st.session_state.stops[0]['full']
    waypoints = [s['full'] for s in st.session_state.stops[1:]]
    
    # Calcul unique avec Google
    res = gmaps.directions(origin, origin, waypoints=waypoints, optimize_waypoints=True)
    
    if res:
        leg_data = res[0]['legs']
        order = res[0]['waypoint_order']
        current_time = datetime.combine(datetime.today(), st.session_state.stops[0]['dep_time'])
        
        st.info(f"Départ prévu à : {current_time.strftime('%H:%M')}")

        for i, leg in enumerate(leg_data[:-1]):
            client_idx = order[i] + 1
            client = st.session_state.stops[client_idx]
            
            travel_min = leg['duration']['value'] / 60
            arrival_time = current_time + timedelta(minutes=travel_min)
            
            # Gestion Latence
            wait_min = 0
            if client.get('use_h'):
                t_open = datetime.combine(datetime.today(), client['t1'])
                if arrival_time < t_open:
                    wait_min = (t_open - arrival_time).seconds / 60
                    st.markdown(f'<div style="border-left:5px solid green; padding:10px; background:#f0fff0">⏳ <b>Attente : {int(wait_min)} min</b> (Ouverture à {client["t1"].strftime("%H:%M")})</div>', unsafe_allow_html=True)
                    arrival_time = t_open

            st.success(f"📍 **{i+1}. {client['full']}** | Arrivée : **{arrival_time.strftime('%H:%M')}**")
            
            stay_dur = client.get('dur', 15)
            current_time = arrival_time + timedelta(minutes=stay_dur)

    if st.button("⬅️ Retourner aux adresses"):
        st.session_state.step = 2
        st.rerun()
