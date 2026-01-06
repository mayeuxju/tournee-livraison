import streamlit as st
import googlemaps
import folium
from streamlit_folium import folium_static
from datetime import datetime, timedelta
import polyline

# --- CONFIGURATION ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

if 'stops' not in st.session_state: st.session_state.stops = []
if 'step' not in st.session_state: st.session_state.step = 2 
if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None

try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except:
    st.error("Clé API manquante dans les Secrets.")
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

# --- AFFICHAGE CARTE ---
def draw_map(stops, route_polyline=None):
    # Centrage sur la Suisse ou le premier point
    center = [46.8, 8.2] if not stops else [stops[0]['lat'], stops[0]['lng']]
    m = folium.Map(location=center, zoom_start=8 if not stops else 12)
    
    for i, s in enumerate(stops):
        color = 'red' if i == 0 else 'blue'
        label = 'DÉPÔT' if i == 0 else f'Client {i}'
        folium.Marker([s['lat'], s['lng']], popup=s['full'], tooltip=label,
                      icon=folium.Icon(color=color, icon='info-sign')).add_to(m)

    if route_polyline:
        decoded = polyline.decode(route_polyline)
        folium.PolyLine(decoded, color="blue", weight=5, opacity=0.7).add_to(m)
        
    folium_static(m, width=800)

# --- ÉTAPE 2 : CONFIGURATION ---
if st.session_state.step == 2:
    st.title("🚛 Configuration de la Tournée")
    col_form, col_map = st.columns([1, 1])
    
    with col_form:
        idx = st.session_state.edit_idx
        is_edit = idx is not None
        is_depot = (not is_edit and len(st.session_state.stops) == 0) or (is_edit and idx == 0)

        st.subheader("🏠 Dépôt" if is_depot else "👤 Ajouter un Client")
        p = st.session_state.stops[idx]['raw'] if is_edit else {"n":"","r":"","npa":"","v":""}
        
        with st.form("add_form"):
            c1, c2 = st.columns([1, 3])
            num = c1.text_input("N°", p['n'])
            rue = c2.text_input("Rue", p['r'])
            c3, c4 = st.columns(2)
            npa = c3.text_input("NPA", p['npa'])
            vil = c4.text_input("Ville", p['v'])
            
            if is_depot:
                h_dep = st.time_input("Heure de départ", datetime.now().replace(hour=8, minute=0))
            else:
                ca, cb = st.columns(2)
                use_h = ca.checkbox("Horaire fixe / impératif")
                dur = cb.number_input("Temps sur place (min)", 5, 120, 15)
                t1 = st.time_input("Pas avant", datetime.now().replace(hour=8, minute=0))
                t2 = st.time_input("Pas après", datetime.now().replace(hour=18, minute=0))

            if st.form_submit_button("Enregistrer l'adresse"):
                res = validate_address(num, rue, npa, vil)
                if res:
                    if is_depot: res["h_dep"] = h_dep
                    else: res.update({"use_h":use_h, "dur":dur, "t1":t1, "t2":t2})
                    
                    if is_edit: st.session_state.stops[idx] = res
                    else: st.session_state.stops.append(res)
                    st.session_state.edit_idx = None
                    st.rerun()
                else: st.error("Adresse introuvable.")

        st.write("---")
        for i, s in enumerate(st.session_state.stops):
            c1, c2 = st.columns([0.8, 0.2])
            c1.write(f"{'🏠' if i==0 else f'📍 {i}'} {s['full']}")
            if c2.button("Modifier", key=f"edit_{i}"):
                st.session_state.edit_idx = i
                st.rerun()

    with col_map:
        draw_map(st.session_state.stops)

    if len(st.session_state.stops) > 1:
        if st.button("🚀 CALCULER L'ITINÉRAIRE OPTIMISÉ", use_container_width=True):
            st.session_state.step = 3
            st.rerun()

# --- ÉTAPE 3 : RÉSULTATS (FEUILLE DE ROUTE) ---
elif st.session_state.step == 3:
    st.title("🏁 Feuille de Route Optimisée")
    
    origin = st.session_state.stops[0]['full']
    destinations = [s['full'] for s in st.session_state.stops[1:]]
    
    res = gmaps.directions(origin, origin, waypoints=destinations, optimize_waypoints=True)
    
    if res:
        legs = res[0]['legs']
        order = res[0]['waypoint_order']
        current_time = datetime.combine(datetime.today(), st.session_state.stops[0]['h_dep'])
        
        st.subheader(f"🕒 Départ du dépôt à {current_time.strftime('%H:%M')}")
        
        for i, leg in enumerate(legs[:-1]):
            # 1. INFO TRAJET
            dist = leg['distance']['text']
            dur_trajet = leg['duration']['text']
            st.markdown(f"<p style='text-align:center; color:gray;'>⬇️ Trajet : {dist} ({dur_trajet}) ⬇️</p>", unsafe_allow_html=True)
            
            arrival_time = current_time + timedelta(seconds=leg['duration']['value'])
            client_idx = order[i] + 1
            client = st.session_state.stops[client_idx]
            
            # 2. LOGIQUE D'ATTENTE (LIGNE VERTE)
            if client.get('use_h'):
                t_open = datetime.combine(datetime.today(), client['t1'])
                if arrival_time < t_open:
                    wait_min = int((t_open - arrival_time).total_seconds() / 60)
                    st.success(f"⏳ **ATTENTE CONSEILLÉE : {wait_min} min** (Ouverture à {client['t1'].strftime('%H:%M')})")
                    arrival_time = t_open

            # 3. BULLE CLIENT
            with st.container():
                st.markdown(f"""
                <div style="border: 2px solid #007bff; padding: 15px; border-radius: 10px; background: white; margin-bottom: 5px;">
                    <h3 style="margin:0; color:#007bff;">📍 {i+1}. {client['full'].split(',')[0]}</h3>
                    <p style="margin:5px 0;"><b>🏠 Adresse :</b> {client['full']}</p>
                    <p style="margin:5px 0;"><b>⌚ Arrivée prévue : {arrival_time.strftime('%H:%M')}</b></p>
                    <p style="margin:5px 0;"><b>📦 Temps sur place :</b> {client['dur']} min</p>
                    {f"<p style='color:green;'><b>🕒 Créneau demandé :</b> {client['t1'].strftime('%H:%M')} - {client['t2'].strftime('%H:%M')}</p>" if client['use_h'] else ""}
                </div>
                """, unsafe_allow_html=True)
                # Champ pour copier l'adresse
                st.text_input("Cliquer pour copier l'adresse :", value=client['full'], key=f"copy_{i}")

            current_time = arrival_time + timedelta(minutes=client['dur'])

        # CARTE FINALE
        st.write("---")
        st.subheader("🗺️ Carte du trajet")
        draw_map(st.session_state.stops, res[0]['overview_polyline']['points'])

    if st.button("⬅️ Modifier la liste des clients"):
        st.session_state.step = 2
        st.rerun()
