import streamlit as st
import googlemaps
import folium
from streamlit_folium import folium_static
from datetime import datetime, timedelta
import polyline

# --- CONFIGURATION ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

# CSS pour harmoniser le style
st.markdown("""
    <style>
    .stCodeBlock { border: none !important; background-color: rgba(255,255,255,0.1) !important; }
    code { color: white !important; font-weight: bold !important; }
    </style>
    """, unsafe_allow_html=True)

if 'stops' not in st.session_state: st.session_state.stops = []
if 'step' not in st.session_state: st.session_state.step = 1 # On commence à l'étape 1 (Véhicule)
if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None
if 'vehicle' not in st.session_state: st.session_state.vehicle = "Voiture"

try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except:
    st.error("Erreur : Clé API Google manquante.")
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
            "npa": f_npa, "ville": f_vil, "raw": {"n":n, "r":r, "npa":npa, "v":v}
        }
    return None

def draw_map(stops, route_polyline=None):
    center = [46.8, 8.2] if not stops else [stops[0]['lat'], stops[0]['lng']]
    m = folium.Map(location=center, zoom_start=8 if not stops else 11)
    for i, s in enumerate(stops):
        folium.Marker([s['lat'], s['lng']], tooltip=f"{s.get('nom', 'Client')}",
                      icon=folium.Icon(color='red' if i==0 else 'blue')).add_to(m)
    if route_polyline:
        folium.PolyLine(polyline.decode(route_polyline), color="#28a745", weight=5).add_to(m)
    folium_static(m, width=700)

# --- ÉTAPE 1 : CHOIX VÉHICULE ---
if st.session_state.step == 1:
    st.title("🚚 Catégorie de véhicule")
    v = st.radio("Choisissez le type de véhicule pour le calcul des temps :", ["Voiture", "Camion (Lourd)"])
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

        st.subheader("🏠 Dépôt" if is_depot else "👤 Nouveau Client")
        p = st.session_state.stops[idx]['raw'] if is_edit else {"n":"","r":"","npa":"","v":""}
        old_nom = st.session_state.stops[idx].get('nom', '') if is_edit else ""

        with st.form("add_form"):
            nom = st.text_input("Nom du Client", "Dépôt" if is_depot else old_nom)
            c1, c2 = st.columns([1, 3])
            num = c1.text_input("N°", p['n'])
            rue = c2.text_input("Rue", p['r'])
            c3, c4 = st.columns(2)
            npa = c3.text_input("NPA", p['npa'])
            vil = c4.text_input("Ville", p['v'])
            
            if is_depot:
                h_dep = st.time_input("Heure de départ du dépôt", datetime.now().replace(hour=8, minute=0))
            else:
                ca, cb = st.columns(2)
                use_h = ca.checkbox("Horaire impératif")
                dur = cb.number_input("Temps sur place (min)", 5, 120, 15)
                t1 = st.time_input("Pas avant", datetime.now().replace(hour=8, minute=0))
                t2 = st.time_input("Pas après", datetime.now().replace(hour=18, minute=0))

            if st.form_submit_button("Enregistrer"):
                res = validate_address(num, rue, npa, vil)
                if res:
                    res["nom"] = "Dépôt" if is_depot else nom
                    if is_depot: res["h_dep"] = h_dep
                    else: res.update({"use_h":use_h, "dur":dur, "t1":t1, "t2":t2})
                    if is_edit: st.session_state.stops[idx] = res
                    else: st.session_state.stops.append(res)
                    st.session_state.edit_idx = None
                    st.rerun()
                else: st.error("Adresse introuvable.")

        for i, s in enumerate(st.session_state.stops):
            c1, c2 = st.columns([0.8, 0.2])
            c1.info(f"**{i}. {s['nom']}** - {s['full']}")
            if c2.button("Modifier", key=f"ed_{i}"):
                st.session_state.edit_idx = i
                st.rerun()

    with col_map:
        draw_map(st.session_state.stops)

    if len(st.session_state.stops) > 1:
        if st.button("🚀 CALCULER L'ITINÉRAIRE", use_container_width=True):
            st.session_state.step = 3
            st.rerun()

# --- ÉTAPE 3 : RÉSULTATS ---
elif st.session_state.step == 3:
    st.title("🏁 Feuille de Route Optimisée")
    
    # Facteur Camion (+20% temps)
    t_mult = 1.2 if st.session_state.vehicle == "Camion (Lourd)" else 1.0
    
    origin = st.session_state.stops[0]['full']
    destinations = [s['full'] for s in st.session_state.stops[1:]]
    res = gmaps.directions(origin, origin, waypoints=destinations, optimize_waypoints=True)
    
    if res:
        order = res[0]['waypoint_order']
        legs = res[0]['legs']
        current_time = datetime.combine(datetime.today(), st.session_state.stops[0]['h_dep'])
        
        st.success(f"🚚 **Véhicule : {st.session_state.vehicle}** | 🕒 Départ : {current_time.strftime('%H:%M')}")
        
        for i, leg in enumerate(legs[:-1]):
            # --- CADRE ORANGE (TRAJET) ---
            dist_km = leg['distance']['text']
            # On ajuste la durée selon le véhicule
            dur_mins = int((leg['duration']['value'] / 60) * t_mult)
            st.markdown(f"""
                <div style="border: 2px solid orange; border-radius: 8px; padding: 5px; text-align: center; margin: 15px 0; color: orange; font-weight: bold;">
                🚗 Trajet : {dist_km} — Env. {dur_mins} mins
                </div>
                """, unsafe_allow_html=True)
            
            arrival_time = current_time + timedelta(minutes=dur_mins)
            client = st.session_state.stops[order[i] + 1]
            
            # LATENCE (VERT)
            if client.get('use_h'):
                t_open = datetime.combine(datetime.today(), client['t1'])
                if arrival_time < t_open:
                    wait_min = int((t_open - arrival_time).total_seconds() / 60)
                    st.markdown(f'<div style="border: 2px solid #28a745; background-color: #d4edda; padding: 10px; border-radius: 5px; margin-bottom: 10px; color: #155724; text-align: center;"><b>🟢 ATTENTE : {wait_min} min</b></div>', unsafe_allow_html=True)
                    arrival_time = t_open

            # --- BULLE CLIENT UNIQUE (BLEUE) ---
            with st.container():
                st.markdown(f"""
                <div style="background-color: #0047AB; color: white; padding: 20px; border-radius: 12px; margin-bottom: 0px;">
                    <h3 style="margin:0; color: white;">{i+1}. {client['nom']}</h3>
                    <p style="margin: 10px 0 5px 0; font-size: 16px;">
                        ⌚ Arrivée : <b>{arrival_time.strftime('%H:%M')}</b> | 📦 Temps sur place : {client['dur']} min
                        {f"<br><span style='color: #90EE90;'>⏱ Créneau : {client['t1'].strftime('%H:%M')} - {client['t2'].strftime('%H:%M')}</span>" if client['use_h'] else ""}
                    </p>
                </div>
                """, unsafe_allow_html=True)
                # Adresse directement dans la bulle via st.code pour copie clic-droit/bouton
                with st.container():
                    st.markdown('<div style="background-color: #0047AB; padding: 0 20px 20px 20px; border-radius: 0 0 12px 12px; margin-top: -5px;">', unsafe_allow_html=True)
                    st.code(client['full'], language="text")
                    st.markdown('</div>', unsafe_allow_html=True)

            current_time = arrival_time + timedelta(minutes=client['dur'])

        st.write("---")
        draw_map(st.session_state.stops, res[0]['overview_polyline']['points'])

    if st.button("⬅️ Modifier la tournée / Véhicule"):
        st.session_state.step = 1
        st.rerun()
