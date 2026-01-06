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
    .summary-box { padding: 6px 12px; border-radius: 8px; margin-bottom: 5px; display: flex; align-items: center; color: white; font-size: 0.9rem; }
    .depot-box { background-color: #28a745; border: 1px solid #1e7e34; } 
    .client-box { background-color: #0047AB; border: 1px solid #003380; }
    [data-testid="stHorizontalBlock"] { align-items: center; }
    .client-card { background-color: #0047AB; color: white; padding: 15px; border-radius: 10px 10px 0 0; margin-top: 10px; }
    .address-box { background-color: #0047AB; padding: 0 15px 10px 15px; border-radius: 0 0 10px 10px; margin-bottom: 10px; }
    .address-box code { color: white !important; background-color: rgba(255,255,255,0.2) !important; border: none !important; }
    .badge { padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; margin-left: 10px; background: rgba(255,255,255,0.2); }
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
    st.session_state.f_type = "Livraison"
    st.session_state.f_dur = 15
    st.session_state.f_use_h = False
    st.session_state.f_t1 = datetime.strptime("08:00", "%H:%M").time()
    st.session_state.f_t2 = datetime.strptime("18:00", "%H:%M").time()
    st.session_state.f_hdep = datetime.strptime("08:00", "%H:%M").time()
    st.session_state.edit_idx = None

if 'f_nom' not in st.session_state: reset_form_fields()

try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except:
    st.error("⚠️ Clé API Google manquante.")
    st.stop()

def validate_address(n, r, npa, v):
    query = f"{r} {n} {npa} {v}, Suisse".strip()
    res = gmaps.geocode(query)
    if res:
        full_addr = res[0]['formatted_address']
        display_addr = full_addr.replace(", Suisse", "").replace(", Switzerland", "")
        return {
            "full": full_addr, "display": display_addr,
            "lat": res[0]['geometry']['location']['lat'],
            "lng": res[0]['geometry']['location']['lng'],
            "raw": {"n":n, "r":r, "npa":npa, "v":v}
        }
    return None

# --- ÉTAPE 1 : VÉHICULE ---
if st.session_state.step == 1:
    st.title("🚚 Type de transport")
    v = st.radio("Sélectionnez votre véhicule :", ["Voiture", "Camion (Lourd)"])
    if st.button("Valider ➡️"):
        st.session_state.vehicle = v
        st.session_state.step = 2
        st.rerun()

# --- ÉTAPE 2 : CONFIGURATION ---
elif st.session_state.step == 2:
    st.title(f"📍 Configuration de la tournée")
    
    col_form, col_map = st.columns([1, 1])

    with col_form:
        idx = st.session_state.edit_idx
        is_edit = idx is not None
        is_depot = (not is_edit and len(st.session_state.stops) == 0) or (is_edit and idx == 0)

        st.subheader("🏠 Dépôt" if is_depot else "👤 Client")
        st.session_state.f_nom = st.text_input("Nom / Enseigne", value=st.session_state.f_nom)
        c1, c2 = st.columns([1, 3])
        st.session_state.f_num = c1.text_input("N°", value=st.session_state.f_num)
        st.session_state.f_rue = c2.text_input("Rue", value=st.session_state.f_rue)
        c3, c4 = st.columns(2)
        st.session_state.f_npa = c3.text_input("NPA", value=st.session_state.f_npa)
        st.session_state.f_vil = c4.text_input("Ville", value=st.session_state.f_vil)
        
        if is_depot:
            st.session_state.f_hdep = st.time_input("Heure de départ", value=st.session_state.f_hdep)
        else:
            cc1, cc2 = st.columns(2)
            st.session_state.f_type = cc1.selectbox("Type de mission", ["Livraison", "Ramasse"])
            st.session_state.f_dur = cc2.number_input("Temps (min)", 5, 120, value=st.session_state.f_dur)
            st.session_state.f_use_h = st.checkbox("Horaire impératif", value=st.session_state.f_use_h)
            if st.session_state.f_use_h:
                ca, cb = st.columns(2)
                st.session_state.f_t1 = ca.time_input("Pas avant", value=st.session_state.f_t1)
                st.session_state.f_t2 = cb.time_input("Pas après", value=st.session_state.f_t2)

        if st.button("✅ Enregistrer", type="primary", use_container_width=True):
            res = validate_address(st.session_state.f_num, st.session_state.f_rue, st.session_state.f_npa, st.session_state.f_vil)
            if res:
                res["nom"] = "DÉPÔT" if is_depot else (st.session_state.f_nom or f"Client {len(st.session_state.stops)}")
                if is_depot: res["h_dep"] = st.session_state.f_hdep
                else: res.update({"type": st.session_state.f_type, "use_h": st.session_state.f_use_h, "dur": st.session_state.f_dur, "t1": st.session_state.f_t1, "t2": st.session_state.f_t2})
                
                if is_edit: st.session_state.stops[idx] = res
                else: st.session_state.stops.append(res)
                reset_form_fields()
                st.rerun()

        if len(st.session_state.stops) > 1:
            st.write("---")
            st.subheader("🚀 Optimisation")
            algo = st.radio("Stratégie de tournée :", 
                           ["Logique Chauffeur (Aller -> Retour)", "Mathématique (Le plus court)"],
                           help="Le mode 'Logique' livre toutes les livraisons à l'aller et fait les ramasses au retour.")
            if st.button("CALCULER L'ITINÉRAIRE", use_container_width=True, type="primary"):
                st.session_state.algo = algo
                st.session_state.step = 3
                st.rerun()

        st.subheader("📋 Liste des arrêts")
        for i, s in enumerate(st.session_state.stops):
            color_class = "depot-box" if i == 0 else "client-box"
            st.markdown(f'<div class="summary-box {color_class}">', unsafe_allow_html=True)
            cols = st.columns([0.05, 0.75, 0.1, 0.1])
            cols[0].write("🏠" if i == 0 else f"{i}")
            type_tag = f'<span class="badge">{"📦 Liv." if s.get("type")=="Livraison" else "🔄 Ram."}</span>' if i > 0 else ""
            cols[1].markdown(f"**{s['nom']}** | {s['display']} {type_tag}", unsafe_allow_html=True)
            if cols[2].button("✏️", key=f"ed_{i}"):
                st.session_state.edit_idx = i
                st.session_state.f_nom, st.session_state.f_num = s['nom'], s['raw']['n']
                st.session_state.f_rue, st.session_state.f_npa, st.session_state.f_vil = s['raw']['r'], s['raw']['npa'], s['raw']['v']
                if i == 0: st.session_state.f_hdep = s['h_dep']
                else:
                    st.session_state.f_dur, st.session_state.f_use_h, st.session_state.f_type = s['dur'], s['use_h'], s['type']
                    st.session_state.f_t1, st.session_state.f_t2 = s['t1'], s['t2']
                st.rerun()
            if cols[3].button("🗑️", key=f"dl_{i}"):
                st.session_state.stops.pop(i)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    with col_map:
        m = folium.Map(location=[46.8, 8.2], zoom_start=7)
        for i, s in enumerate(st.session_state.stops):
            folium.Marker([s['lat'], s['lng']], tooltip=s['nom'], icon=folium.Icon(color="green" if i==0 else "blue")).add_to(m)
        folium_static(m, width=600)

# --- ÉTAPE 3 : RÉSULTATS ---
elif st.session_state.step == 3:
    st.title("🏁 Itinéraire Optimisé")
    t_mult = 1.25 if st.session_state.vehicle == "Camion (Lourd)" else 1.0
    depot = st.session_state.stops[0]
    
    # --- LOGIQUE DE TRI ---
    clients = st.session_state.stops[1:]
    
    if st.session_state.algo == "Logique Chauffeur (Aller -> Retour)":
        # On sépare Livraisons et Ramasses
        livraisons = [c for c in clients if c['type'] == "Livraison"]
        ramasses = [c for c in clients if c['type'] == "Ramasse"]
        
        # Tri simple par distance au dépôt (à vol d'oiseau pour la logique)
        # Livraisons : de la plus proche à la plus loin
        livraisons.sort(key=lambda x: ((x['lat']-depot['lat'])**2 + (x['lng']-depot['lng'])**2))
        # Ramasses : de la plus loin à la plus proche (retour vers dépôt)
        ramasses.sort(key=lambda x: ((x['lat']-depot['lat'])**2 + (x['lng']-depot['lng'])**2), reverse=True)
        
        ordered_clients = livraisons + ramasses
        # On demande à Google de calculer le trajet dans cet ordre PRÉCIS (sans ré-optimiser)
        waypoints = [c['full'] for c in ordered_clients]
        res = gmaps.directions(depot['full'], depot['full'], waypoints=waypoints, optimize_waypoints=False)
        order = list(range(len(ordered_clients)))
    else:
        # Optimisation Google classique (Mathématique)
        waypoints = [c['full'] for c in clients]
        res = gmaps.directions(depot['full'], depot['full'], waypoints=waypoints, optimize_waypoints=True)
        order = res[0]['waypoint_order']
        ordered_clients = [clients[i] for i in order]

    if res:
        legs = res[0]['legs']
        current_time = datetime.combine(datetime.today(), depot['h_dep'])
        m_final = folium.Map(location=[depot['lat'], depot['lng']], zoom_start=10)
        st.success(f"🏠 **DÉPART DU DÉPÔT : {current_time.strftime('%H:%M')}**")

        for i, leg in enumerate(legs[:-1]):
            dur_mins = int((leg['duration']['value'] / 60) * t_mult)
            st.markdown(f'<div style="border: 2px solid #FF8C00; border-radius: 10px; padding: 5px; text-align: center; margin: 15px 0; color: #FF8C00; font-weight: bold;">⏱️ Trajet : {leg["distance"]["text"]} ({dur_mins} min)</div>', unsafe_allow_html=True)
            
            arrival_time = current_time + timedelta(minutes=dur_mins)
            client = ordered_clients[i]
            
            if client['use_h'] and arrival_time < datetime.combine(datetime.today(), client['t1']):
                arrival_time = datetime.combine(datetime.today(), client['t1'])

            type_icon = "📦" if client['type'] == "Livraison" else "🔄"
            st.markdown(f'<div class="client-card"><h3 style="margin:0; color: white;">{i+1}. {type_icon} {client["nom"]}</h3><p style="margin: 5px 0; opacity: 0.9;">⌚ Arrivée : <b>{arrival_time.strftime("%H:%M")}</b> | {client["type"]} ({client["dur"]} min)</p></div>', unsafe_allow_html=True)
            st.markdown('<div class="address-box">', unsafe_allow_html=True)
            st.code(client['full'], language=None)
            st.markdown('</div>', unsafe_allow_html=True)

            folium.Marker([client['lat'], client['lng']], popup=client['nom'], icon=folium.Icon(color="blue")).add_to(m_final)
            current_time = arrival_time + timedelta(minutes=client['dur'])

        folium.PolyLine(polyline.decode(res[0]['overview_polyline']['points']), color="blue", weight=5).add_to(m_final)
        folium_static(m_final, width=1000)

        if st.button("⬅️ Modifier"):
            st.session_state.step = 2
            st.rerun()
