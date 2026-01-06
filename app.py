import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time as time_module
import copy

st.set_page_config(page_title="Tournées Suisse 🚚", layout="wide", initial_sidebar_state="collapsed")

# CSS Mobile-Friendly
st.markdown("""
<style>
    /* Mode mobile optimisé */
    @media (max-width: 768px) {
        .block-container {
            padding: 1rem 0.5rem !important;
        }
        h1 {
            font-size: 1.5rem !important;
        }
        h2 {
            font-size: 1.2rem !important;
        }
        h3 {
            font-size: 1rem !important;
        }
        .stButton button {
            font-size: 0.9rem !important;
            padding: 0.4rem 0.8rem !important;
        }
        .stMetric {
            background: #f8f9fa;
            padding: 0.5rem;
            border-radius: 8px;
            margin: 0.2rem 0;
        }
        .stMetric label {
            font-size: 0.75rem !important;
        }
        .stMetric [data-testid="stMetricValue"] {
            font-size: 1rem !important;
        }
    }
    
    /* Carte de livraison */
    .delivery-card {
        background: white;
        border: 2px solid #e0e0e0;
        border-radius: 12px;
        padding: 1rem;
        margin: 0.8rem 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    
    .delivery-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.8rem;
    }
    
    .delivery-number {
        background: #1f77b4;
        color: white;
        border-radius: 50%;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        font-size: 1rem;
    }
    
    .delivery-client {
        font-size: 1.1rem;
        font-weight: bold;
        color: #333;
        flex: 1;
        margin: 0 0.5rem;
    }
    
    .delivery-address {
        font-size: 0.9rem;
        color: #666;
        margin: 0.4rem 0;
    }
    
    .delivery-creneau {
        background: #fff3cd;
        padding: 0.3rem 0.6rem;
        border-radius: 6px;
        font-size: 0.85rem;
        color: #856404;
        display: inline-block;
        margin: 0.3rem 0;
    }
    
    .delivery-stats {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 0.5rem;
        margin-top: 0.8rem;
    }
    
    .stat-box {
        background: #f8f9fa;
        padding: 0.5rem;
        border-radius: 8px;
        text-align: center;
    }
    
    .stat-label {
        font-size: 0.75rem;
        color: #666;
        display: block;
    }
    
    .stat-value {
        font-size: 1rem;
        font-weight: bold;
        color: #333;
        display: block;
        margin-top: 0.2rem;
    }
    
    /* Latence */
    .latence-bar {
        background: linear-gradient(90deg, #90EE90 0%, #98FB98 100%);
        padding: 0.8rem;
        border-radius: 10px;
        margin: 0.8rem 0;
        border-left: 5px solid #32CD32;
        text-align: center;
    }
    
    .latence-time {
        font-size: 1.2rem;
        font-weight: bold;
        color: #2d5016;
    }
    
    .latence-subtitle {
        font-size: 0.85rem;
        color: #666;
        margin-top: 0.3rem;
    }
    
    /* Conflits */
    .conflict-alert {
        background: #f8d7da;
        border: 2px solid #f5c6cb;
        border-radius: 10px;
        padding: 0.8rem;
        margin: 0.5rem 0;
    }
    
    .conflict-title {
        font-weight: bold;
        color: #721c24;
        font-size: 1rem;
    }
    
    .conflict-message {
        color: #721c24;
        font-size: 0.9rem;
        margin-top: 0.3rem;
    }
    
    /* Boutons actions */
    .action-buttons {
        display: flex;
        gap: 0.5rem;
        justify-content: flex-end;
        margin-top: 0.5rem;
    }
    
    /* Résumé final */
    .summary-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.2rem;
        border-radius: 12px;
        margin: 1rem 0;
    }
    
    .summary-title {
        font-size: 1.2rem;
        font-weight: bold;
        margin-bottom: 0.8rem;
    }
    
    .summary-stats {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 0.8rem;
    }
    
    .summary-stat {
        text-align: center;
    }
    
    .summary-stat-label {
        font-size: 0.8rem;
        opacity: 0.9;
    }
    
    .summary-stat-value {
        font-size: 1.3rem;
        font-weight: bold;
        margin-top: 0.2rem;
    }
    
    /* Sélecteur véhicule */
    .vehicle-selector {
        background: #e3f2fd;
        border: 2px solid #90caf9;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

st.title("🚚 Tournées Suisse")

# Initialiser
if 'livraisons' not in st.session_state:
    st.session_state.livraisons = []
if 'depot' not in st.session_state:
    st.session_state.depot = None
if 'historique' not in st.session_state:
    st.session_state.historique = []
if 'mode_edition' not in st.session_state:
    st.session_state.mode_edition = None
if 'insert_latence' not in st.session_state:
    st.session_state.insert_latence = None
if 'type_vehicule' not in st.session_state:
    st.session_state.type_vehicule = "Camion"

geolocator = Nominatim(user_agent="delivery_optimizer_ch_v6")

# Fonction pour convertir minutes en HH:MM
def minutes_to_hhmm(minutes):
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"

# Fonction pour obtenir la vitesse selon le véhicule
def get_vehicle_speed(vehicle_type):
    speeds = {
        "Camion": 50,      # km/h
        "Camionnette": 65, # km/h
        "Voiture": 80      # km/h
    }
    return speeds.get(vehicle_type, 60)

# Fonction pour géocoder une adresse en Suisse
def geocode_address_ch(numero, rue, npa, ville):
    parts = []
    if numero and rue:
        parts.append(f"{numero} {rue}")
    elif rue:
        parts.append(rue)
    
    if npa:
        parts.append(str(npa))
    if ville:
        parts.append(ville)
    
    if not parts:
        return None, None
    
    parts.append("Suisse")
    address = ", ".join(parts)
    
    try:
        location = geolocator.geocode(address, timeout=10)
        if location:
            return (location.latitude, location.longitude), address
    except:
        pass
    return None, None

# Fonction pour calculer temps de trajet
def time_diff_minutes(time1, time2):
    dt1 = datetime.combine(datetime.today(), time1)
    dt2 = datetime.combine(datetime.today(), time2)
    return int((dt2 - dt1).total_seconds() / 60)

# Fonction d'optimisation
def optimize_route_with_conflicts(depot_coords, deliveries, heure_depart, vehicle_speed):
    if not deliveries or not depot_coords:
        return [], []
    
    current_time = datetime.strptime(heure_depart, "%H:%M")
    current_pos = depot_coords
    
    with_slots = [d for d in deliveries if d['creneau_debut'] or d['creneau_fin']]
    without_slots = [d for d in deliveries if not d['creneau_debut'] and not d['creneau_fin']]
    
    route = []
    conflicts = []
    remaining_with_slots = with_slots.copy()
    remaining_without_slots = without_slots.copy()
    
    while remaining_with_slots or remaining_without_slots:
        best_delivery = None
        best_distance = float('inf')
        has_conflict = False
        
        for delivery in remaining_with_slots:
            distance = geodesic(current_pos, delivery['coords']).km
            travel_time = int((distance / vehicle_speed) * 60)
            arrival_time = (current_time + timedelta(minutes=travel_time)).time()
            
            debut = delivery['creneau_debut']
            fin = delivery['creneau_fin']
            
            conflict_info = None
            
            if fin and arrival_time > fin:
                minutes_late = time_diff_minutes(fin, arrival_time)
                conflict_info = f"⚠️ CONFLIT : Arrivée à {arrival_time.strftime('%H:%M')}, créneau fermé à {fin.strftime('%H:%M')} (retard: {minutes_late} min)"
                has_conflict = True
            
            if debut and arrival_time < debut:
                wait_time = time_diff_minutes(arrival_time, debut)
                if wait_time > 120:
                    conflict_info = f"⚠️ CONFLIT : Arrivée à {arrival_time.strftime('%H:%M')}, créneau commence à {debut.strftime('%H:%M')} (attente: {minutes_to_hhmm(wait_time)})"
                    has_conflict = True
                else:
                    arrival_time = debut
            
            if not has_conflict or not best_delivery:
                if distance < best_distance:
                    best_distance = distance
                    best_delivery = delivery
                    if conflict_info:
                        delivery['conflict'] = conflict_info
        
        if not best_delivery and remaining_without_slots:
            best_delivery = min(remaining_without_slots, 
                              key=lambda d: geodesic(current_pos, d['coords']).km)
        
        if not best_delivery and remaining_with_slots:
            best_delivery = min(remaining_with_slots,
                              key=lambda d: geodesic(current_pos, d['coords']).km)
        
        if best_delivery:
            distance = geodesic(current_pos, best_delivery['coords']).km
            travel_time = int((distance / vehicle_speed) * 60)
            arrival_time_dt = current_time + timedelta(minutes=travel_time)
            arrival_time = arrival_time_dt.time()
            
            latence = 0
            if best_delivery['creneau_debut']:
                debut_dt = datetime.combine(datetime.today(), best_delivery['creneau_debut'])
                if arrival_time_dt < debut_dt:
                    latence = time_diff_minutes(arrival_time, best_delivery['creneau_debut'])
                    arrival_time_dt = debut_dt
                    arrival_time = best_delivery['creneau_debut']
            
            if best_delivery['creneau_fin'] and arrival_time > best_delivery['creneau_fin']:
                minutes_late = time_diff_minutes(best_delivery['creneau_fin'], arrival_time)
                conflicts.append({
                    'client': best_delivery['Client'],
                    'type': 'RETARD',
                    'message': f"Arrivée à {arrival_time.strftime('%H:%M')}, créneau fermé à {best_delivery['creneau_fin'].strftime('%H:%M')}",
                    'retard': minutes_to_hhmm(minutes_late)
                })
            
            best_delivery['heure_arrivee'] = arrival_time
            best_delivery['distance_depuis_precedent'] = distance
            best_delivery['duree_trajet'] = travel_time
            best_delivery['latence'] = latence if latence > 0 else None
            
            route.append(best_delivery)
            
            current_pos = best_delivery['coords']
            manutention = best_delivery['duree_manutention'] or 10
            current_time = arrival_time_dt + timedelta(minutes=manutention)
            
            if best_delivery in remaining_with_slots:
                remaining_with_slots.remove(best_delivery)
            if best_delivery in remaining_without_slots:
                remaining_without_slots.remove(best_delivery)
        else:
            break
    
    return route, conflicts

# Fonction pour sauvegarder dans l'historique
def save_to_history():
    if 'route_optimized' in st.session_state and st.session_state.route_optimized:
        snapshot = {
            'timestamp': datetime.now().strftime("%d/%m %H:%M"),
            'depot': copy.deepcopy(st.session_state.depot),
            'livraisons': copy.deepcopy(st.session_state.livraisons),
            'route': copy.deepcopy(st.session_state.route_optimized),
            'vehicule': st.session_state.type_vehicule
        }
        st.session_state.historique.insert(0, snapshot)
        if len(st.session_state.historique) > 5:
            st.session_state.historique.pop()

# ===== SECTION 1 : CHOIX VÉHICULE + DÉPÔT =====
with st.expander("🚛 Configuration", expanded=not st.session_state.depot):
    
    # Choix véhicule
    st.markdown("### Type de véhicule")
    col_v1, col_v2, col_v3 = st.columns(3)
    
    with col_v1:
        if st.button("🚚 Camion\n(50 km/h)", 
                    type="primary" if st.session_state.type_vehicule == "Camion" else "secondary",
                    use_container_width=True):
            st.session_state.type_vehicule = "Camion"
            if 'route_optimized' in st.session_state:
                del st.session_state.route_optimized
            st.rerun()
    
    with col_v2:
        if st.button("🚐 Camionnette\n(65 km/h)", 
                    type="primary" if st.session_state.type_vehicule == "Camionnette" else "secondary",
                    use_container_width=True):
            st.session_state.type_vehicule = "Camionnette"
            if 'route_optimized' in st.session_state:
                del st.session_state.route_optimized
            st.rerun()
    
    with col_v3:
        if st.button("🚗 Voiture\n(80 km/h)", 
                    type="primary" if st.session_state.type_vehicule == "Voiture" else "secondary",
                    use_container_width=True):
            st.session_state.type_vehicule = "Voiture"
            if 'route_optimized' in st.session_state:
                del st.session_state.route_optimized
            st.rerun()
    
    st.info(f"**Véhicule actuel** : {st.session_state.type_vehicule} ({get_vehicle_speed(st.session_state.type_vehicule)} km/h)")
    
    st.divider()
    
    # Point de départ
    st.markdown("### 🏭 Point de départ")
    
    depot_col1, depot_col2 = st.columns([1, 3])
    with depot_col1:
        depot_numero = st.text_input("N°", key="depot_numero", placeholder="12")
    with depot_col2:
        depot_rue = st.text_input("Rue", key="depot_rue", placeholder="Rue de la Gare")
    
    depot_col3, depot_col4 = st.columns([1, 2])
    with depot_col3:
        depot_npa = st.text_input("NPA", key="depot_npa", placeholder="1003")
    with depot_col4:
        depot_ville = st.text_input("Ville", key="depot_ville", placeholder="Lausanne")
    
    heure_depart = st.time_input("⏰ Heure de départ", 
                                 value=datetime.strptime("08:00", "%H:%M").time(), 
                                 key="heure_depart")
    
    if st.button("✅ Valider", type="primary", use_container_width=True):
        if not heure_depart:
            st.error("❌ L'heure de départ est obligatoire !")
        elif not (depot_npa or depot_ville):
            st.error("❌ Renseignez au moins le NPA ou la Ville")
        else:
            with st.spinner("🔍 Géolocalisation..."):
                coords, full_address = geocode_address_ch(depot_numero, depot_rue, depot_npa, depot_ville)
                if coords:
                    st.session_state.depot = {
                        'adresse': full_address,
                        'coords': coords,
                        'heure_depart': heure_depart.strftime("%H:%M")
                    }
                    st.success(f"✅ {full_address}")
                    st.rerun()
                else:
                    st.error("❌ Adresse introuvable")

if st.session_state.depot:
    st.success(f"📍 **{st.session_state.depot['adresse']}** | 🕐 {st.session_state.depot['heure_depart']}")

# ===== SECTION 2 : AJOUT/ÉDITION LIVRAISONS =====
if st.session_state.mode_edition is not None:
    st.markdown("---")
    st.subheader("✏️ Modifier")
    idx = st.session_state.mode_edition
    livraison = st.session_state.livraisons[idx]
    
    with st.form("edit_form"):
        nom_edit = st.text_input("Client", value=livraison['Client'])
        
        col_num, col_rue = st.columns([1, 3])
        with col_num:
            numero_edit = st.text_input("N°", value=livraison.get('numero', ''))
        with col_rue:
            rue_edit = st.text_input("Rue", value=livraison.get('rue', ''))
        
        col_npa, col_ville = st.columns([1, 2])
        with col_npa:
            npa_edit = st.text_input("NPA", value=livraison.get('npa', ''))
        with col_ville:
            ville_edit = st.text_input("Ville", value=livraison.get('ville', ''))
        
        st.markdown("**Créneau (optionnel)**")
        col_time1, col_time2 = st.columns(2)
        with col_time1:
            debut_edit = st.time_input("De", value=livraison.get('creneau_debut'), key="debut_edit")
        with col_time2:
            fin_edit = st.time_input("À", value=livraison.get('creneau_fin'), key="fin_edit")
        
        manut_edit = st.number_input("Manutention (min)", min_value=0, 
                                    value=livraison.get('duree_manutention') or 0)
        
        col_submit, col_cancel = st.columns(2)
        
        with col_submit:
            if st.form_submit_button("💾 OK", type="primary", use_container_width=True):
                if nom_edit and (npa_edit or ville_edit):
                    with st.spinner("🔍"):
                        coords, full_address = geocode_address_ch(numero_edit, rue_edit, npa_edit, ville_edit)
                        if coords:
                            st.session_state.livraisons[idx] = {
                                'Client': nom_edit,
                                'numero': numero_edit,
                                'rue': rue_edit,
                                'npa': npa_edit,
                                'ville': ville_edit,
                                'Adresse': full_address,
                                'creneau_debut': debut_edit,
                                'creneau_fin': fin_edit,
                                'duree_manutention': manut_edit if manut_edit > 0 else None,
                                'coords': coords
                            }
                            st.session_state.mode_edition = None
                            if 'route_optimized' in st.session_state:
                                del st.session_state.route_optimized
                            st.rerun()
                        else:
                            st.error("❌ Adresse introuvable")
        
        with col_cancel:
            if st.form_submit_button("❌", use_container_width=True):
                st.session_state.mode_edition = None
                st.rerun()

elif st.session_state.insert_latence is not None:
    st.markdown("---")
    st.subheader(f"➕ Ajouter (position {st.session_state.insert_latence + 1})")
    
    with st.form("insert_latence_form", clear_on_submit=True):
        nom_lat = st.text_input("Client", placeholder="Client urgent")
        
        col_num, col_rue = st.columns([1, 3])
        with col_num:
            numero_lat = st.text_input("N°", placeholder="5")
        with col_rue:
            rue_lat = st.text_input("Rue", placeholder="Avenue...")
        
        col_npa, col_ville = st.columns([1, 2])
        with col_npa:
            npa_lat = st.text_input("NPA", placeholder="1000")
        with col_ville:
            ville_lat = st.text_input("Ville", placeholder="Lausanne")
        
        st.markdown("**Créneau (optionnel)**")
        col_time1, col_time2 = st.columns(2)
        with col_time1:
            debut_lat = st.time_input("De", value=None, key="debut_lat")
        with col_time2:
            fin_lat = st.time_input("À", value=None, key="fin_lat")
        
        manut_lat = st.number_input("Manutention (min)", min_value=0, value=0)
        
        col_submit, col_cancel = st.columns(2)
        
        with col_submit:
            if st.form_submit_button("➕ OK", type="primary", use_container_width=True):
                if nom_lat and (npa_lat or ville_lat):
                    with st.spinner("🔍"):
                        coords, full_address = geocode_address_ch(numero_lat, rue_lat, npa_lat, ville_lat)
                        if coords:
                            new_delivery = {
                                'Client': nom_lat,
                                'numero': numero_lat,
                                'rue': rue_lat,
                                'npa': npa_lat,
                                'ville': ville_lat,
                                'Adresse': full_address,
                                'creneau_debut': debut_lat,
                                'creneau_fin': fin_lat,
                                'duree_manutention': manut_lat if manut_lat > 0 else None,
                                'coords': coords
                            }
                            position = st.session_state.insert_latence
                            st.session_state.livraisons.insert(position, new_delivery)
                            st.session_state.insert_latence = None
                            if 'route_optimized' in st.session_state:
                                del st.session_state.route_optimized
                            st.rerun()
        
        with col_cancel:
            if st.form_submit_button("❌", use_container_width=True):
                st.session_state.insert_latence = None
                st.rerun()

else:
    with st.expander("➕ Ajouter une livraison", expanded=len(st.session_state.livraisons) == 0):
        with st.form("ajout_form", clear_on_submit=True):
            nom = st.text_input("Client", placeholder="Restaurant...")
            
            col_num, col_rue = st.columns([1, 3])
            with col_num:
                numero = st.text_input("N°", placeholder="15")
            with col_rue:
                rue = st.text_input("Rue", placeholder="Avenue de la Gare")
            
            col_npa, col_ville = st.columns([1, 2])
            with col_npa:
                npa = st.text_input("NPA", placeholder="1003")
            with col_ville:
                ville = st.text_input("Ville", placeholder="Lausanne")
            
            st.markdown("**Créneau (optionnel)**")
            col_time1, col_time2 = st.columns(2)
            with col_time1:
                creneau_debut = st.time_input("De", value=None, key="debut")
            with col_time2:
                creneau_fin = st.time_input("À", value=None, key="fin")
            
            duree_manutention = st.number_input("Manutention (min)", min_value=0, value=0, 
                                               help="0 = 10 min par défaut")
            
            if st.form_submit_button("➕ Ajouter", type="primary", use_container_width=True):
                if nom and (npa or ville):
                    with st.spinner("🔍"):
                        time_module.sleep(0.3)
                        coords, full_address = geocode_address_ch(numero, rue, npa, ville)
                        
                        if coords:
                            st.session_state.livraisons.append({
                                'Client': nom,
                                'numero': numero,
                                'rue': rue,
                                'npa': npa,
                                'ville': ville,
                                'Adresse': full_address,
                                'creneau_debut': creneau_debut,
                                'creneau_fin': creneau_fin,
                                'duree_manutention': duree_manutention if duree_manutention > 0 else None,
                                'coords': coords
                            })
                            if 'route_optimized' in st.session_state:
                                del st.session_state.route_optimized
                            st.rerun()
                        else:
                            st.error(f"❌ Adresse introuvable")
                else:
                    st.error("⚠️ Nom + NPA/Ville requis")

# ===== SECTION 3 : HISTORIQUE =====
if st.session_state.historique:
    with st.expander(f"🕐 Historique ({len(st.session_state.historique)})"):
        for idx, snapshot in enumerate(st.session_state.historique):
            col_hist1, col_hist2 = st.columns([3, 1])
            with col_hist1:
                st.write(f"**{snapshot['timestamp']}** - {snapshot['vehicule']} - {len(snapshot['livraisons'])} liv.")
            with col_hist2:
                if st.button("↩️", key=f"restore_{idx}", help="Restaurer"):
                    st.session_state.depot = copy.deepcopy(snapshot['depot'])
                    st.session_state.livraisons = copy.deepcopy(snapshot['livraisons'])
                    st.session_state.route_optimized = copy.deepcopy(snapshot['route'])
                    st.session_state.type_vehicule = snapshot['vehicule']
                    st.rerun()

st.markdown("---")

# ===== SECTION 4 : TOURNÉE =====
st.subheader(f"📋 Tournée ({len(st.session_state.livraisons)})")

if st.session_state.livraisons:
    
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    
    with col_btn1:
        if st.button("🚀 OPTIMISER", type="primary", use_container_width=True):
            if not st.session_state.depot:
                st.error("❌ Définissez le dépôt !")
            else:
                with st.spinner("⏳ Calcul..."):
                    save_to_history()
                    vehicle_speed = get_vehicle_speed(st.session_state.type_vehicule)
                    route, conflicts = optimize_route_with_conflicts(
                        st.session_state.depot['coords'],
                        st.session_state.livraisons,
                        st.session_state.depot['heure_depart'],
                        vehicle_speed
                    )
                    st.session_state.route_optimized = route
                    st.session_state.conflicts = conflicts
                    st.rerun()
    
    with col_btn2:
        if st.button("🔄 Réinit", use_container_width=True):
            if 'route_optimized' in st.session_state:
                del st.session_state.route_optimized
            if 'conflicts' in st.session_state:
                del st.session_state.conflicts
            st.rerun()
    
    with col_btn3:
        if st.button("🗑️ Tout", use_container_width=True):
            st.session_state.livraisons = []
            st.session_state.depot = None
            if 'route_optimized' in st.session_state:
                del st.session_state.route_optimized
            st.rerun()
    
    # Affichage des conflits
    if 'conflicts' in st.session_state and st.session_state.conflicts:
        st.markdown("### ⚠️ Conflits")
        for conflict in st.session_state.conflicts:
            st.markdown(f"""
            <div class="conflict-alert">
                <div class="conflict-title">{conflict['client']}</div>
                <div class="conflict-message">{conflict['message']} | Retard : {conflict['retard']}</div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("---")
    
    # Affichage des résultats optimisés
    if 'route_optimized' in st.session_state and st.session_state.route_optimized:
        
        total_distance = 0
        total_latence = 0
        
        for i, delivery in enumerate(st.session_state.route_optimized):
            total_distance += delivery.get('distance_depuis_precedent', 0)
            
            # Carte de livraison
            creneau_html = ""
            if delivery['creneau_debut'] and delivery['creneau_fin']:
                creneau_html = f'<div class="delivery-creneau">🕐 {delivery["creneau_debut"].strftime("%H:%M")}-{delivery["creneau_fin"].strftime("%H:%M")}</div>'
            elif delivery['creneau_debut']:
                creneau_html = f'<div class="delivery-creneau">🕐 Après {delivery["creneau_debut"].strftime("%H:%M")}</div>'
            elif delivery['creneau_fin']:
                creneau_html = f'<div class="delivery-creneau">🕐 Avant {delivery["creneau_fin"].strftime("%H:%M")}</div>'
            
            st.markdown(f"""
            <div class="delivery-card">
                <div class="delivery-header">
                    <div class="delivery-number">{i+1}</div>
                    <div class="delivery-client">{delivery['Client']}</div>
                </div>
                <div class="delivery-address">{delivery['Adresse']}</div>
                {creneau_html}
                <div class="delivery-stats">
                    <div class="stat-box">
                        <span class="stat-label">🕐 Arrivée</span>
                        <span class="stat-value">{delivery['heure_arrivee'].strftime('%H:%M')}</span>
                    </div>
                    <div class="stat-box">
                        <span class="stat-label">📦 Manut.</span>
                        <span class="stat-value">{minutes_to_hhmm(delivery['duree_manutention'] or 10)}</span>
                    </div>
                    <div class="stat-box">
                        <span class="stat-label">🚗 Distance</span>
                        <span class="stat-value">{delivery.get('distance_depuis_precedent', 0):.1f} km</span>
                    </div>
                    <div class="stat-box">
                        <span class="stat-label">⏱️ Trajet</span>
                        <span class="stat-value">{minutes_to_hhmm(delivery.get('duree_trajet', 0))}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Boutons édition/suppression
            col_edit, col_delete = st.columns(2)
            with col_edit:
                if st.button("✏️ Modifier", key=f"edit_{i}", use_container_width=True):
                    for idx, liv in enumerate(st.session_state.livraisons):
                        if liv['Client'] == delivery['Client'] and liv['Adresse'] == delivery['Adresse']:
                            st.session_state.mode_edition = idx
                            st.rerun()
            with col_delete:
                if st.button("🗑️ Supprimer", key=f"delete_{i}", use_container_width=True):
                    st.session_state.livraisons = [
                        liv for liv in st.session_state.livraisons 
                        if not (liv['Client'] == delivery['Client'] and liv['Adresse'] == delivery['Adresse'])
                    ]
                    del st.session_state.route_optimized
                    st.rerun()
            
            # Afficher latence si > 15 min
            latence = delivery.get('latence', 0)
            if latence and latence > 15:
                total_latence += latence
                
                st.markdown(f"""
                <div class="latence-bar">
                    <div class="latence-time">⏳ LATENCE : {minutes_to_hhmm(latence)}</div>
                    <div class="latence-subtitle">Attente avant ouverture créneau</div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"➕ Ajouter client pendant latence", key=f"add_latence_{i}", use_container_width=True):
                    st.session_state.insert_latence = i
                    st.rerun()
        
        # Retour dépôt
        st.markdown("### 🏁 Retour dépôt")
        last_pos = st.session_state.route_optimized[-1]['coords']
        distance_retour = geodesic(last_pos, st.session_state.depot['coords']).km
        total_distance += distance_retour
        vehicle_speed = get_vehicle_speed(st.session_state.type_vehicule)
        duree_retour = int((distance_retour / vehicle_speed) * 60)
        
        col_ret1, col_ret2 = st.columns(2)
        with col_ret1:
            st.metric("🚗 Distance", f"{distance_retour:.1f} km")
        with col_ret2:
            st.metric("⏱️ Temps", minutes_to_hhmm(duree_retour))
        
        st.markdown("---")
        
        # Résumé final
        duree_totale_route = int((total_distance / vehicle_speed) * 60)
        temps_manutention = sum(d['duree_manutention'] or 10 for d in st.session_state.route_optimized)
        duree_totale = duree_totale_route + temps_manutention + total_latence
        
        heure_fin = datetime.strptime(st.session_state.depot['heure_depart'], "%H:%M") + timedelta(minutes=duree_totale)
        
        st.markdown(f"""
        <div class="summary-box">
            <div class="summary-title">📊 RÉSUMÉ DE LA TOURNÉE</div>
            <div class="summary-stats">
                <div class="summary-stat">
                    <div class="summary-stat-label">📏 Distance</div>
                    <div class="summary-stat-value">{total_distance:.1f} km</div>
                </div>
                <div class="summary-stat">
                    <div class="summary-stat-label">🚗 Route</div>
                    <div class="summary-stat-value">{minutes_to_hhmm(duree_totale_route)}</div>
                </div>
                <div class="summary-stat">
                    <div class="summary-stat-label">📦 Manut.</div>
                    <div class="summary-stat-value">{minutes_to_hhmm(temps_manutention)}</div>
                </div>
                <div class="summary-stat">
                    <div class="summary-stat-label">⏳ Latence</div>
                    <div class="summary-stat-value">{minutes_to_hhmm(total_latence) if total_latence > 0 else "—"}</div>
                </div>
            </div>
            <div style="text-align: center; margin-top: 1rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.3);">
                <div style="font-size: 0.9rem; opacity: 0.9;">⏱️ Durée totale</div>
                <div style="font-size: 1.8rem; font-weight: bold; margin-top: 0.3rem;">{minutes_to_hhmm(duree_totale)}</div>
                <div style="font-size: 1rem; margin-top: 0.5rem;">🏁 Retour estimé : {heure_fin.strftime('%H:%M')}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Export
        st.markdown("---")
        
        waypoints = [f"{d['coords'][0]},{d['coords'][1]}" for d in st.session_state.route_optimized]
        depot_coords = st.session_state.depot['coords']
        
        google_url = f"https://www.google.com/maps/dir/?api=1&origin={depot_coords[0]},{depot_coords[1]}&destination={depot_coords[0]},{depot_coords[1]}&waypoints={'|'.join(waypoints)}&travelmode=driving"
        
        col_export1, col_export2 = st.columns(2)
        
        with col_export1:
            st.link_button("🗺️ GOOGLE MAPS", google_url, type="primary", use_container_width=True)
        
        with col_export2:
            route_data = []
            for i, d in enumerate(st.session_state.route_optimized, 1):
                route_data.append({
                    'N°': i,
                    'Client': d['Client'],
                    'Adresse': d['Adresse'],
                    'Arrivée': d['heure_arrivee'].strftime('%H:%M'),
                    'Manutention': minutes_to_hhmm(d['duree_manutention'] or 10),
                    'Distance': f"{d.get('distance_depuis_precedent', 0):.1f} km"
                })
            
            df = pd.DataFrame(route_data)
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 CSV", csv, "tournee.csv", "text/csv", use_container_width=True)
    
    else:
        # Liste simple
        st.info("👇 Vos livraisons (non optimisées)")
        
        for idx, d in enumerate(st.session_state.livraisons):
            col1, col2, col3 = st.columns([5, 1, 1])
            
            with col1:
                creneau_str = ""
                if d['creneau_debut'] and d['creneau_fin']:
                    creneau_str = f" | 🕐 {d['creneau_debut'].strftime('%H:%M')}-{d['creneau_fin'].strftime('%H:%M')}"
                elif d['creneau_debut']:
                    creneau_str = f" | 🕐 Après {d['creneau_debut'].strftime('%H:%M')}"
                elif d['creneau_fin']:
                    creneau_str = f" | 🕐 Avant {d['creneau_fin'].strftime('%H:%M')}"
                
                st.write(f"**{idx + 1}. {d['Client']}**")
                st.caption(f"{d['Adresse']}{creneau_str}")
            
            with col2:
                if st.button("✏️", key=f"edit_simple_{idx}", help="Modifier"):
                    st.session_state.mode_edition = idx
                    st.rerun()
            
            with col3:
                if st.button("🗑️", key=f"delete_simple_{idx}", help="Supprimer"):
                    st.session_state.livraisons.pop(idx)
                    st.rerun()
        
        st.warning("⚠️ Cliquez sur **OPTIMISER** pour calculer l'itinéraire")

else:
    st.info("👆 Configurez le dépôt puis ajoutez des livraisons")
