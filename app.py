import streamlit as st
import googlemaps
from datetime import datetime, timedelta
import folium
from streamlit_folium import folium_static

# --- CONFIGURATION ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

if 'stops' not in st.session_state: st.session_state.stops = []
if 'step' not in st.session_state: st.session_state.step = 1
if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None

try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except:
    st.error("Clé API manquante.")
    st.stop()

# --- FONCTIONS UTILES ---
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

def render_summary():
    if st.session_state.stops:
        st.write("---")
        st.subheader("📍 Résumé de la configuration")
        for i, stop in enumerate(st.session_state.stops):
            c1, c2, c3 = st.columns([0.1, 0.7, 0.2])
            c1.write("🏠" if i==0 else f"📍 {i}")
            with c2:
                txt = f"**{stop['full']}**"
                if i > 0 and stop.get('use_h'):
                    txt += f" | 🕒 {stop['t1'].strftime('%H:%M')} - {stop['t2'].strftime('%H:%M')}"
                st.markdown(txt + " ✅")
            if c3.button("Modifier", key=f"edit_{i}"):
                st.session_state.edit_idx = i
                st.rerun()

# --- ÉTAPE 2 : CONFIGURATION ---
if st.session_state.step == 2:
    idx = st.session_state.edit_idx
    is_editing = idx is not None
    is_depot = (not is_editing and len(st.session_state.stops) == 0) or (is_editing and idx == 0)

    st.title("🏠 Dépôt" if is_depot else "👤 Client")
    
    p = st.session_state.stops[idx]['raw'] if is_editing else {"n":"","r":"","npa":"","v":""}
    
    with st.form("form_stop"):
        c1, c2, c3, c4 = st.columns([1,3,1,2])
        num = c1.text_input("N°", p['n'])
        rue = c2.text_input("Rue", p['r'])
        npa = c3.text_input("NPA", p['npa'])
        vil = c4.text_input("Ville", p['v'])
        
        if is_depot:
            dep_time = st.time_input("Heure de départ", datetime.now().replace(hour=8, minute=0))
        else:
            ch1, ch2, ch3 = st.columns(3)
            use_h = ch1.checkbox("Horaire impératif ?")
            t1 = ch2.time_input("Pas avant", datetime.now().replace(hour=8, minute=0))
            t2 = ch3.time_input("Pas après", datetime.now().replace(hour=18, minute=0))
            dur = st.slider("Durée sur place (min)", 5, 120, 15)

        if st.form_submit_button("✅ Valider"):
            data = validate_address(num, rue, npa, vil)
            if data:
                if is_depot: data["dep_time"] = dep_time
                else: data.update({"t1":t1, "t2":t2, "dur":dur, "use_h":use_h})
                
                if is_editing: st.session_state.stops[idx] = data
                else: st.session_state.stops.append(data)
                st.session_state.edit_idx = None
                st.rerun()

    if len(st.session_state.stops) > 1:
        if st.button("🚀 LANCER LA TOURNÉE"):
            st.session_state.step = 3
            st.rerun()
    render_summary()

# --- ÉTAPE 3 : RÉSULTATS AVEC ANALYSE DE LATENCE ---
elif st.session_state.step == 3:
    st.title("🏁 Feuille de Route & Analyse")
    
    # 1. Calcul Google pour l'ordre optimal
    origin = st.session_state.stops[0]['full']
    waypoints = [s['full'] for s in st.session_state.stops[1:]]
    res = gmaps.directions(origin, origin, waypoints=waypoints, optimize_waypoints=True)
    
    if res:
        leg_data = res[0]['legs']
        order = res[0]['waypoint_order'] # Ex: [1, 0] signifie que le 2ème client saisi est le 1er à livrer
        
        current_time = datetime.combine(datetime.today(), st.session_state.stops[0]['dep_time'])
        st.write(f"🟢 **Départ du dépôt à {current_time.strftime('%H:%M')}**")
        
        for i, leg in enumerate(leg_data[:-1]): # On ignore le retour au dépôt pour cet exemple
            # Trouver quel client est à cette étape
            client_idx = order[i] + 1
            client = st.session_state.stops[client_idx]
            
            # Temps de trajet
            travel_min = leg['duration']['value'] / 60
            arrival_time = current_time + timedelta(minutes=travel_min)
            
            # --- LOGIQUE DE LATENCE ET CONFLIT ---
            wait_min = 0
            conflict = False
            
            if client.get('use_h'):
                t_open = datetime.combine(datetime.today(), client['t1'])
                t_close = datetime.combine(datetime.today(), client['t2'])
                
                if arrival_time < t_open:
                    wait_min = (t_open - arrival_time).seconds / 60
                elif arrival_time > t_close:
                    conflict = True

            # Affichage de la ligne de trajet
            st.write(f"🚚 *Trajet : {int(travel_min)} min*")

            # Affichage LATENCE (Ligne verte)
            if wait_min > 15:
                st.markdown(f"""
                <div style="border-left: 10px solid #28a745; background: #eaffea; padding: 10px; margin: 5px 0; border-radius: 5px;">
                    <b>⏳ LATENCE : {int(wait_min)} min d'attente</b><br>
                    <small>Arrivée à {arrival_time.strftime('%H:%M')} | Ouverture à {client['t1'].strftime('%H:%M')}<br>
                    💡 <i>Conseil : Vous pouvez ajouter un client ici.</i></small>
                </div>
                """, unsafe_allow_html=True)
                current_time = t_open # On attend l'ouverture
            else:
                current_time = arrival_time

            # Affichage CONFLIT (Ligne rouge)
            if conflict:
                st.error(f"⚠️ CONFLIT : Arrivée à {arrival_time.strftime('%H:%M')} chez {client['full']} (ferme à {client['t2'].strftime('%H:%M')})")

            # Affichage de l'étape
            st.success(f"📍 **{i+1}. {client['full']}** (Arrivée : {current_time.strftime('%H:%M')})")
            
            # Temps sur place
            stay_dur = client.get('dur', 15)
            current_time += timedelta(minutes=stay_dur)
            st.write(f"📦 Service : {stay_dur} min")

    if st.button("⬅️ Revenir à la configuration"):
        st.session_state.step = 2
        st.rerun()
