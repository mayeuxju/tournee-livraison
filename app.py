import streamlit as st
import googlemaps
import folium
from streamlit_folium import folium_static
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

if 'stops' not in st.session_state: st.session_state.stops = []
if 'step' not in st.session_state: st.session_state.step = 1
if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None
if 'result' not in st.session_state: st.session_state.result = None

try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except:
    st.error("Clé API Google manquante dans les Secrets.")
    st.stop()

# --- LOGIQUE ADRESSE ---
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

# --- UI : RÉSUMÉ & CARTE ---
def render_summary():
    if st.session_state.stops:
        st.write("---")
        st.subheader("📍 Étapes actuelles")
        for i, stop in enumerate(st.session_state.stops):
            col_icon, col_txt, col_edit = st.columns([0.1, 0.7, 0.2])
            with col_icon: st.write("🏠" if i==0 else f"📍 {i}")
            with col_txt:
                st.markdown(f"**{stop['full']}**", unsafe_allow_html=True)
            with col_edit:
                if st.button("📝 Modifier", key=f"edit_{i}"):
                    st.session_state.edit_idx = i
                    st.rerun()
        
        # Carte simple de prévisualisation
        m = folium.Map(location=[st.session_state.stops[0]['lat'], st.session_state.stops[0]['lng']], zoom_start=11)
        for i, s in enumerate(st.session_state.stops):
            folium.Marker([s['lat'], s['lng']], popup=s['full']).add_to(m)
        folium_static(m)

# --- ÉTAPE 1 : VÉHICULE ---
if st.session_state.step == 1:
    st.title("🚚 Type de véhicule")
    v_type = st.radio("Catégorie", ["Voiture / Utilitaire (Vitesse max)", "Poids Lourd (Réglementé 80km/h)"])
    if st.button("Continuer ➡️"):
        st.session_state.vehicule = v_type
        st.session_state.step = 2
        st.rerun()

# --- ÉTAPE 2 : SAISIE ---
elif st.session_state.step == 2:
    idx = st.session_state.edit_idx
    is_editing = idx is not None
    is_depot = (not is_editing and len(st.session_state.stops) == 0) or (is_editing and idx == 0)

    st.title("🏠 Point de départ" if is_depot else "👤 Ajouter un client")
    
    p = st.session_state.stops[idx]['raw'] if is_editing else {"n":"","r":"","npa":"","v":""}
    
    with st.form("add_stop"):
        c1, c2, c3, c4 = st.columns([1,3,1,2])
        num = c1.text_input("N°", p['n'])
        rue = c2.text_input("Rue", p['r'])
        npa = c3.text_input("NPA", p['npa'])
        vil = c4.text_input("Ville", p['v'])
        
        if is_depot:
            dep_time = st.time_input("Heure de départ du dépôt", datetime.now().replace(hour=8, minute=0))
        else:
            c_h1, c_h2, c_dur = st.columns(3)
            use_h = st.checkbox("Activer contrainte horaire ?")
            t1 = c_h1.time_input("Dès", datetime.now().replace(hour=8, minute=0))
            t2 = c_h2.time_input("Jusqu'à", datetime.now().replace(hour=18, minute=0))
            dur = c_dur.number_input("Temps d'arrêt (min)", 15)

        if st.form_submit_button("✅ Valider l'adresse"):
            data = validate_address(num, rue, npa, vil)
            if data:
                if is_depot: data["dep_time"] = dep_time
                else:
                    data.update({"t1": t1, "t2": t2, "dur": dur, "use_h": use_h})
                
                if is_editing: st.session_state.stops[idx] = data
                else: st.session_state.stops.append(data)
                st.session_state.edit_idx = None
                st.rerun()
            else:
                st.error("Adresse non trouvée. Vérifiez les champs.")

    if len(st.session_state.stops) > 1:
        if st.button("🚀 CALCULER L'ITINÉRAIRE OPTIMISÉ", type="primary"):
            # Lancement du calcul Google
            with st.spinner("Optimisation du trajet en cours..."):
                origin = st.session_state.stops[0]['full']
                # On utilise le dépôt comme destination pour faire une boucle (facultatif)
                destination = origin 
                waypoints = [s['full'] for s in st.session_state.stops[1:]]
                
                directions_result = gmaps.directions(
                    origin, destination, 
                    waypoints=waypoints, 
                    optimize_waypoints=True, # C'est ICI que l'optimisation se fait
                    mode="driving",
                    departure_time="now"
                )
                
                if directions_result:
                    st.session_state.result = directions_result[0]
                    st.session_state.step = 3
                    st.rerun()

    render_summary()

# --- ÉTAPE 3 : RÉSULTATS ---
elif st.session_state.step == 3:
    st.title("🏁 Votre Feuille de Route Optimisée")
    
    res = st.session_state.result
    waypoint_order = res['waypoint_order'] # L'ordre calculé par Google
    legs = res['legs']
    
    # Heure de départ
    current_time = datetime.combine(datetime.today(), st.session_state.stops[0]['dep_time'])
    
    # Affichage
    for i, leg in enumerate(legs):
        # Point de départ du segment
        st.info(f"📍 **{i+1}. {leg['start_address']}**")
        
        # Détails du trajet
        dist = leg['distance']['text']
        dur_sec = leg['duration']['value']
        # Ajustement si Poids Lourd (+20% de temps)
        if st.session_state.vehicule == "Poids Lourd (Réglementé 80km/h)":
            dur_sec *= 1.2
            
        current_time += timedelta(seconds=dur_sec)
        
        st.markdown(f"➡️ *Trajet de {dist} (~{int(dur_sec/60)} min)*")
        st.success(f"⏱️ **Arrivée prévue : {current_time.strftime('%H:%M')}**")
        
        # Temps d'arrêt (sauf au dernier point)
        if i < len(legs) - 1:
            # On retrouve le temps d'arrêt prévu pour ce waypoint
            stop_idx = waypoint_order[i] + 1
            service_time = st.session_state.stops[stop_idx].get('dur', 15)
            current_time += timedelta(minutes=service_time)
            st.write(f"📦 Travail sur place : {service_time} min")

    if st.button("⬅️ Modifier les adresses"):
        st.session_state.step = 2
        st.rerun()
