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
    .summary-box { padding: 6px 12px; border-radius: 8px; margin-bottom: 5px; display: flex; align-items: center; color: white; font-size: 0.85rem; }
    .depot-box { background-color: #28a745; border: 1px solid #1e7e34; } 
    .client-box { background-color: #0047AB; border: 1px solid #003380; }
    [data-testid="stHorizontalBlock"] { align-items: center; }
    
    /* Style de la fiche client finale */
    .client-card { background-color: #0047AB; color: white; padding: 15px; border-radius: 10px 10px 0 0; margin-top: 10px; }
    .address-box { background-color: #0047AB; padding: 0 15px 10px 15px; border-radius: 0 0 10px 10px; margin-bottom: 10px; }
    .address-box code { color: white !important; background-color: rgba(255,255,255,0.2) !important; border: none !important; }
    
    /* Badge horaire dans la liste */
    .time-badge { color: #FFD700; font-weight: bold; font-size: 0.8rem; text-align: center; border: 1px dashed #FFD700; padding: 2px 5px; border-radius: 4px; }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISATION ---
if 'stops' not in st.session_state: st.session_state.stops = []
if 'step' not in st.session_state: st.session_state.step = 1
if 'vehicle' not in st.session_state: st.session_state.vehicle = "Voiture"
if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None

# --- FONCTIONS ---
def reset_form_fields():
    st.session_state.f_nom = ""; st.session_state.f_num = ""; st.session_state.f_rue = ""; 
    st.session_state.f_npa = ""; st.session_state.f_vil = ""; st.session_state.f_dur = 10; 
    st.session_state.f_use_h = False; st.session_state.edit_idx = None

# --- LOGIQUE D'OPTIMISATION ---
def get_optimized_order(clients, mode):
    if not clients: return []
    if mode == "Mathématique (Le plus court)":
        return list(range(len(clients))) # Google s'en chargera
    else:
        # LOGIQUE CHAUFFEUR : Livraisons d'abord (croissant), puis Ramasses (décroissant)
        # On calcule la distance à vol d'oiseau simplifiée par rapport au dépôt (index 0)
        depot = st.session_state.stops[0]
        for c in clients:
            c['dist_ref'] = abs(c['lat'] - depot['lat']) + abs(c['lng'] - depot['lng'])
        
        livraisons = [c for c in clients if c['type'] == "Livraison"]
        ramasses = [c for c in clients if c['type'] == "Ramasse"]
        
        # Livraisons : de la plus proche à la plus lointaine
        livraisons.sort(key=lambda x: x['dist_ref'])
        # Ramasses : de la plus lointaine à la plus proche
        ramasses.sort(key=lambda x: x['dist_ref'], reverse=True)
        
        ordered = livraisons + ramasses
        # Retourne les index originaux dans le nouvel ordre
        return [clients.index(c) for c in ordered]

# --- UI ---
gmaps = googlemaps.Client(key=st.secrets["GMAPS_API_KEY"])

# ÉTAPE 1 : DÉPÔT
if st.session_state.step == 1:
    st.title("🚩 Point de départ")
    with st.form("depot_form"):
        col1, col2 = st.columns(2)
        nom = col1.text_input("Nom du dépôt (ex: Entrepôt Principal)")
        adresse = col2.text_input("Adresse complète (Rue, N°, NPA, Ville)")
        h_dep = st.time_input("Heure de départ", datetime.strptime("08:00", "%H:%M"))
        
        if st.form_submit_button("Valider le dépôt"):
            res = gmaps.geocode(adresse)
            if res:
                geo = res[0]['geometry']['location']
                comp = res[0]['address_components']
                npa = next((c['long_name'] for c in comp if 'postal_code' in c['types']), "")
                ville = next((c['long_name'] for c in comp if 'locality' in c['types']), "")
                rue = next((c['long_name'] for c in comp if 'route' in c['types']), "")
                num = next((c['long_name'] for c in comp if 'street_number' in c['types']), "")
                
                st.session_state.stops = [{
                    'nom': nom, 'lat': geo['lat'], 'lng': geo['lng'],
                    'full': f"{rue} {num}, {npa} {ville}", 'h_dep': h_dep
                }]
                st.session_state.step = 2
                st.rerun()
            else:
                st.error("Adresse introuvable.")

# ÉTAPE 2 : CLIENTS
elif st.session_state.step == 2:
    depot = st.session_state.stops[0]
    st.title("📦 Gestion des arrêts")
    
    # Bouton d'optimisation en haut
    col_opt, col_mode = st.columns([1, 1])
    mode_opt = col_mode.radio("Stratégie de route :", ["Mathématique (Le plus court)", "Logique Chauffeur (Aller -> Retour)"], horizontal=True)
    if col_opt.button("🚀 OPTIMISER LA TOURNÉE", use_container_width=True, type="primary"):
        if len(st.session_state.stops) > 1:
            st.session_state.mode_opt = mode_opt
            st.session_state.step = 3
            st.rerun()

    # Formulaire de saisie
    with st.expander(f"➕ Ajouter / Modifier un client", expanded=True):
        with st.form("client_form", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            f_nom = c1.text_input("Nom du client", key="f_nom")
            f_type = c2.selectbox("Type de mission", ["Livraison", "Ramasse"])
            f_dur = c3.number_input("Temps sur place (min)", min_value=0, key="f_dur")
            
            c4, c5, c6, c7 = st.columns([3, 1, 1, 2])
            f_rue = c4.text_input("Rue", key="f_rue")
            f_num = c5.text_input("N°", key="f_num")
            f_npa = c6.text_input("NPA", key="f_npa")
            f_vil = c7.text_input("Ville", key="f_vil")
            
            cc1, cc2, cc3 = st.columns([1, 1, 1])
            f_use_h = cc1.checkbox("Horaire impératif ?", key="f_use_h")
            f_t1 = cc2.time_input("Pas avant", datetime.strptime("08:00", "%H:%M")) if f_use_h else None
            f_t2 = cc3.time_input("Pas après", datetime.strptime("18:00", "%H:%M")) if f_use_h else None
            
            if st.form_submit_button("Enregistrer le client"):
                full_addr = f"{f_rue} {f_num}, {f_npa} {f_vil}, Suisse"
                res = gmaps.geocode(full_addr)
                if res:
                    geo = res[0]['geometry']['location']
                    comp = res[0]['address_components']
                    clean_npa = next((c['long_name'] for c in comp if 'postal_code' in c['types']), f_npa)
                    clean_vil = next((c['long_name'] for c in comp if 'locality' in c['types']), f_vil)
                    clean_rue = next((c['long_name'] for c in comp if 'route' in c['types']), f_rue)
                    clean_num = next((c['long_name'] for c in comp if 'street_number' in c['types']), f_num)
                    
                    new_client = {
                        'nom': f_nom, 'lat': geo['lat'], 'lng': geo['lng'], 'type': f_type,
                        'full': f"{clean_rue} {clean_num}, {clean_npa} {clean_vil}",
                        'dur': f_dur, 'use_h': f_use_h, 't1': f_t1, 't2': f_t2
                    }
                    if st.session_state.edit_idx is not None:
                        st.session_state.stops[st.session_state.edit_idx] = new_client
                    else:
                        st.session_state.stops.append(new_client)
                    reset_form_fields()
                    st.rerun()
                else:
                    st.error("⚠️ Adresse introuvable, veuillez vérifier.")

    # Liste des arrêts (Résumé)
    st.subheader(f"📍 Liste des arrêts ({len(st.session_state.stops)-1})")
    for i, s in enumerate(st.session_state.stops):
        is_depot = (i == 0)
        bg_class = "depot-box" if is_depot else "client-box"
        label = "DÉPÔT" if is_depot else s['type'][:4]
        
        # Formatage de l'horaire pour la liste
        time_display = ""
        if not is_depot:
            time_display = f"{s['t1'].strftime('%H:%M')} - {s['t2'].strftime('%H:%M')}" if s['use_h'] else "Libre"

        with st.container():
            cols = st.columns([0.5, 2.5, 4.5, 1.2, 2, 0.8, 0.8])
            cols[0].markdown(f'<div class="summary-box {bg_class}">{i}</div>', unsafe_allow_html=True)
            cols[1].write(f"**{s['nom']}**")
            cols[2].write(f"{s['full']}")
            if not is_depot:
                cols[3].markdown(f'<div class="summary-box {bg_class}" style="justify-content:center;">{label}</div>', unsafe_allow_html=True)
                cols[4].markdown(f'<div class="time-badge">🕒 {time_display}</div>', unsafe_allow_html=True)
                if cols[5].button("📝", key=f"edit_{i}"):
                    st.session_state.edit_idx = i
                    # Pré-remplissage (simplifié pour l'exemple)
                    st.rerun()
                if cols[6].button("🗑️", key=f"del_{i}"):
                    st.session_state.stops.pop(i)
                    st.rerun()
            else:
                cols[3].markdown(f'<div class="summary-box {bg_class}" style="justify-content:center;">{label}</div>', unsafe_allow_html=True)
                cols[4].write(f"Départ: {s['h_dep'].strftime('%H:%M')}")

# ÉTAPE 3 : FEUILLE DE ROUTE
elif st.session_state.step == 3:
    st.title("🏁 Votre Feuille de Route")
    
    depot = st.session_state.stops[0]
    clients = st.session_state.stops[1:]
    
    # Calcul de l'ordre
    custom_order = get_optimized_order(clients, st.session_state.mode_opt)
    
    res = gmaps.directions(
        (depot['lat'], depot['lng']),
        (depot['lat'], depot['lng']),
        waypoints=[(clients[i]['lat'], clients[i]['lng']) for i in custom_order],
        optimize_waypoints=(st.session_state.mode_opt == "Mathématique (Le plus court)"),
        mode="driving", region="ch"
    )

    if res:
        order = res[0]['waypoint_order']
        legs = res[0]['legs']
        m_final = folium.Map(location=[depot['lat'], depot['lng']], zoom_start=10)
        
        current_time = datetime.combine(datetime.today(), depot['h_dep'])
        
        # Affichage Dépôt
        st.markdown(f'<div style="background-color: #28a745; color: white; padding: 10px; border-radius: 10px; margin-bottom: 10px;">🏠 <b>DÉPART : {depot["nom"]}</b> ({depot["h_dep"].strftime("%H:%M")})</div>', unsafe_allow_html=True)
        folium.Marker([depot['lat'], depot['lng']], popup="Dépôt", icon=folium.Icon(color="green")).add_to(m_final)

        for i, leg in enumerate(legs[:-1]):
            dur_mins = int((leg['duration']['value'] / 60) * (1.25 if st.session_state.vehicle == "Camion" else 1.0))
            st.markdown(f'<div style="border-left: 3px dashed #FF8C00; margin-left: 20px; padding-left: 20px; color: #FF8C00; font-weight: bold; font-size: 0.9rem;">⏱️ {leg["distance"]["text"]} ({dur_mins} min)</div>', unsafe_allow_html=True)
            
            arrival_time = current_time + timedelta(minutes=dur_mins)
            client = clients[custom_order[order[i]]]
            
            # Attente si avance sur l'horaire
            wait_msg = ""
            if client['use_h'] and arrival_time < datetime.combine(datetime.today(), client['t1']):
                wait_time = int((datetime.combine(datetime.today(), client['t1']) - arrival_time).total_seconds() / 60)
                arrival_time = datetime.combine(datetime.today(), client['t1'])
                wait_msg = f" <span style='color: #FFD700;'>(Attente: {wait_time} min)</span>"

            # Alertes contraintes
            warning = ""
            if client['use_h'] and arrival_time.time() > client['t2']:
                warning = "⚠️ <b style='color: #FF4B4B;'>RETARD PRÉVU</b>"

            type_icon = "📦" if client['type'] == "Livraison" else "🔄"
            constraint_txt = f" | 🕒 Contrainte: {client['t1'].strftime('%H:%M')}-{client['t2'].strftime('%H:%M')}" if client['use_h'] else ""

            # AFFICHAGE FINAL CLIENT
            st.markdown(f'''
                <div class="client-card">
                    <h3 style="margin:0; color: white;">{i+1}. {type_icon} {client["nom"]} {warning}</h3>
                    <p style="margin: 5px 0; opacity: 0.9;">
                        ⌚ Arrivée : <b>{arrival_time.strftime("%H:%M")}</b>{wait_msg} | 
                        {client["type"]} ({client["dur"]} min){constraint_txt}
                    </p>
                </div>
            ''', unsafe_allow_html=True)
            st.markdown('<div class="address-box">', unsafe_allow_html=True)
            st.code(client['full'], language=None)
            st.markdown('</div>', unsafe_allow_html=True)

            folium.Marker([client['lat'], client['lng']], popup=client['nom'], icon=folium.Icon(color="blue")).add_to(m_final)
            current_time = arrival_time + timedelta(minutes=client['dur'])

        # Retour Dépôt
        st.markdown(f'<div style="background-color: #28a745; color: white; padding: 10px; border-radius: 10px; margin-top: 10px;">🏁 <b>RETOUR DÉPÔT : {current_time.strftime("%H:%M")}</b></div>', unsafe_allow_html=True)

        folium.PolyLine(polyline.decode(res[0]['overview_polyline']['points']), color="blue", weight=5).add_to(m_final)
        folium_static(m_final, width=1000)

        if st.button("⬅️ Modifier la liste"):
            st.session_state.step = 2
            st.rerun()
