import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time as time_module
import copy

st.set_page_config(page_title="Tournées Suisse 🚚", layout="wide")

st.title("🚚 Optimiseur de Tournées - Suisse")
st.markdown("**Édition individuelle + Latence interactive + Historique**")

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

geolocator = Nominatim(user_agent="delivery_optimizer_ch_v5")

# Fonction pour convertir minutes en HH:MM
def minutes_to_hhmm(minutes):
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"

# Fonction pour géocoder une adresse en Suisse
def geocode_address_ch(numero, rue, npa, ville):
    # Construire l'adresse complète
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
        return None
    
    parts.append("Suisse")
    address = ", ".join(parts)
    
    try:
        location = geolocator.geocode(address, timeout=10)
        if location:
            return (location.latitude, location.longitude), address
    except:
        pass
    return None, None

# Fonction pour vérifier si une heure est dans un créneau
def time_diff_minutes(time1, time2):
    dt1 = datetime.combine(datetime.today(), time1)
    dt2 = datetime.combine(datetime.today(), time2)
    return int((dt2 - dt1).total_seconds() / 60)

# Fonction d'optimisation
def optimize_route_with_conflicts(depot_coords, deliveries, heure_depart):
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
            travel_time = int((distance / 60) * 60)  # Vitesse 60 km/h (Suisse)
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
            travel_time = int((distance / 60) * 60)
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
            'timestamp': datetime.now().strftime("%d/%m/%Y %H:%M"),
            'depot': copy.deepcopy(st.session_state.depot),
            'livraisons': copy.deepcopy(st.session_state.livraisons),
            'route': copy.deepcopy(st.session_state.route_optimized)
        }
        st.session_state.historique.insert(0, snapshot)
        if len(st.session_state.historique) > 5:
            st.session_state.historique.pop()

# ===== SECTION 1 : DÉPÔT =====
st.header("🏭 Point de départ")

col_depot1, col_depot2 = st.columns([3, 1])

with col_depot1:
    depot_col1, depot_col2, depot_col3, depot_col4 = st.columns([1, 3, 1, 2])
    
    with depot_col1:
        depot_numero = st.text_input("N°", key="depot_numero", placeholder="12")
    with depot_col2:
        depot_rue = st.text_input("Rue", key="depot_rue", placeholder="Rue de la Gare")
    with depot_col3:
        depot_npa = st.text_input("NPA", key="depot_npa", placeholder="1003")
    with depot_col4:
        depot_ville = st.text_input("Ville", key="depot_ville", placeholder="Lausanne")

with col_depot2:
    heure_depart = st.time_input("⏰ Heure de départ", value=datetime.strptime("08:00", "%H:%M").time(), key="heure_depart")
    
    if st.button("📍 Valider le dépôt", type="primary", use_container_width=True):
        if not heure_depart:
            st.error("❌ L'heure de départ est obligatoire !")
        elif not (depot_npa or depot_ville):
            st.error("❌ Renseignez au moins le NPA ou la Ville")
        else:
            with st.spinner("🔍 Géolocalisation..."):
                result = geocode_address_ch(depot_numero, depot_rue, depot_npa, depot_ville)
                if result[0]:
                    coords, full_address = result
                    st.session_state.depot = {
                        'adresse': full_address,
                        'coords': coords,
                        'heure_depart': heure_depart.strftime("%H:%M")
                    }
                    st.success(f"✅ Dépôt : {full_address}")
                    st.rerun()
                else:
                    st.error("❌ Adresse introuvable")

if st.session_state.depot:
    st.info(f"📍 **Dépôt** : {st.session_state.depot['adresse']} | 🕐 Départ : **{st.session_state.depot['heure_depart']}**")

st.divider()

# ===== SECTION 2 : AJOUT/ÉDITION LIVRAISONS =====
if st.session_state.mode_edition is not None:
    st.header("✏️ Modifier une livraison")
    idx = st.session_state.mode_edition
    livraison = st.session_state.livraisons[idx]
    
    with st.form("edit_form"):
        col1, col2 = st.columns(2)
        
        with col1:
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
        
        with col2:
            st.markdown("**Créneau horaire (optionnel)**")
            col_time1, col_time2 = st.columns(2)
            with col_time1:
                debut_edit = st.time_input("De", value=livraison.get('creneau_debut'), key="debut_edit")
            with col_time2:
                fin_edit = st.time_input("À", value=livraison.get('creneau_fin'), key="fin_edit")
            
            manut_edit = st.number_input("Temps manutention (min)", min_value=0, 
                                        value=livraison.get('duree_manutention') or 0)
        
        col_submit, col_cancel = st.columns(2)
        
        with col_submit:
            if st.form_submit_button("💾 Enregistrer", type="primary", use_container_width=True):
                if nom_edit and (npa_edit or ville_edit):
                    with st.spinner("🔍 Géolocalisation..."):
                        result = geocode_address_ch(numero_edit, rue_edit, npa_edit, ville_edit)
                        if result[0]:
                            coords, full_address = result
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
                            st.success("✅ Livraison modifiée")
                            st.rerun()
                        else:
                            st.error("❌ Adresse introuvable")
                else:
                    st.error("⚠️ Renseignez au moins le nom et NPA/Ville")
        
        with col_cancel:
            if st.form_submit_button("❌ Annuler", use_container_width=True):
                st.session_state.mode_edition = None
                st.rerun()

elif st.session_state.insert_latence is not None:
    st.header("➕ Ajouter un client pendant la latence")
    position = st.session_state.insert_latence
    
    st.info(f"📍 Ce client sera inséré à la position {position + 1}")
    
    with st.form("insert_latence_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            nom_lat = st.text_input("Client", placeholder="Ex: Client urgent")
            
            col_num, col_rue = st.columns([1, 3])
            with col_num:
                numero_lat = st.text_input("N°", placeholder="5")
            with col_rue:
                rue_lat = st.text_input("Rue", placeholder="Avenue de la Gare")
            
            col_npa, col_ville = st.columns([1, 2])
            with col_npa:
                npa_lat = st.text_input("NPA", placeholder="1000")
            with col_ville:
                ville_lat = st.text_input("Ville", placeholder="Lausanne")
        
        with col2:
            st.markdown("**Créneau horaire (optionnel)**")
            col_time1, col_time2 = st.columns(2)
            with col_time1:
                debut_lat = st.time_input("De", value=None, key="debut_lat")
            with col_time2:
                fin_lat = st.time_input("À", value=None, key="fin_lat")
            
            manut_lat = st.number_input("Temps manutention (min)", min_value=0, value=0)
        
        col_submit, col_cancel = st.columns(2)
        
        with col_submit:
            if st.form_submit_button("➕ Insérer", type="primary", use_container_width=True):
                if nom_lat and (npa_lat or ville_lat):
                    with st.spinner("🔍 Géolocalisation..."):
                        result = geocode_address_ch(numero_lat, rue_lat, npa_lat, ville_lat)
                        if result[0]:
                            coords, full_address = result
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
                            st.session_state.livraisons.insert(position, new_delivery)
                            st.session_state.insert_latence = None
                            if 'route_optimized' in st.session_state:
                                del st.session_state.route_optimized
                            st.success(f"✅ Client inséré à la position {position + 1}")
                            st.rerun()
                        else:
                            st.error("❌ Adresse introuvable")
                else:
                    st.error("⚠️ Renseignez au moins le nom et NPA/Ville")
        
        with col_cancel:
            if st.form_submit_button("❌ Annuler", use_container_width=True):
                st.session_state.insert_latence = None
                st.rerun()

else:
    st.header("📦 Ajouter une livraison")
    
    with st.form("ajout_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            nom = st.text_input("Client", placeholder="Ex: Restaurant Chez Pierre")
            
            col_num, col_rue = st.columns([1, 3])
            with col_num:
                numero = st.text_input("N°", placeholder="15", key="add_numero")
            with col_rue:
                rue = st.text_input("Rue", placeholder="Avenue de la Gare", key="add_rue")
            
            col_npa, col_ville = st.columns([1, 2])
            with col_npa:
                npa = st.text_input("NPA", placeholder="1003", key="add_npa")
            with col_ville:
                ville = st.text_input("Ville", placeholder="Lausanne", key="add_ville")
        
        with col2:
            st.markdown("**Créneau horaire (optionnel)**")
            col_time1, col_time2 = st.columns(2)
            with col_time1:
                creneau_debut = st.time_input("De", value=None, key="debut")
            with col_time2:
                creneau_fin = st.time_input("À", value=None, key="fin")
            
            duree_manutention = st.number_input("Temps manutention (min)", min_value=0, value=0, 
                                               help="Laissez à 0 pour 10 min par défaut")
        
        if st.form_submit_button("➕ Ajouter la livraison", type="primary", use_container_width=True):
            if nom and (npa or ville):
                with st.spinner("🔍 Géolocalisation..."):
                    time_module.sleep(0.3)
                    result = geocode_address_ch(numero, rue, npa, ville)
                    
                    if result[0]:
                        coords, full_address = result
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
                        st.success(f"✅ {nom} ajouté")
                        st.rerun()
                    else:
                        st.error(f"❌ Adresse introuvable")
            else:
                st.error("⚠️ Renseignez au moins le nom et NPA/Ville")

st.divider()

# ===== SECTION 3 : HISTORIQUE =====
if st.session_state.historique:
    with st.expander("🕐 Historique des 5 derniers trajets"):
        for idx, snapshot in enumerate(st.session_state.historique):
            col_hist1, col_hist2 = st.columns([4, 1])
            with col_hist1:
                st.write(f"**{idx + 1}.** {snapshot['timestamp']} - {len(snapshot['livraisons'])} livraisons")
            with col_hist2:
                if st.button("↩️ Restaurer", key=f"restore_{idx}"):
                    st.session_state.depot = copy.deepcopy(snapshot['depot'])
                    st.session_state.livraisons = copy.deepcopy(snapshot['livraisons'])
                    st.session_state.route_optimized = copy.deepcopy(snapshot['route'])
                    st.success("✅ Trajet restauré")
                    st.rerun()

st.divider()

# ===== SECTION 4 : LISTE ET OPTIMISATION =====
st.header(f"🗺️ Tournée ({len(st.session_state.livraisons)} livraisons)")

if st.session_state.livraisons:
    
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    
    with col_btn1:
        if st.button("🚀 OPTIMISER LA TOURNÉE", type="primary", use_container_width=True):
            if not st.session_state.depot:
                st.error("❌ Définissez d'abord le dépôt !")
            else:
                with st.spinner("⏳ Optimisation en cours..."):
                    save_to_history()
                    route, conflicts = optimize_route_with_conflicts(
                        st.session_state.depot['coords'],
                        st.session_state.livraisons,
                        st.session_state.depot['heure_depart']
                    )
                    st.session_state.route_optimized = route
                    st.session_state.conflicts = conflicts
                    st.success("✅ Tournée optimisée !")
                    st.rerun()
    
    with col_btn2:
        if st.button("🔄 Réinitialiser la tournée", use_container_width=True):
            if 'route_optimized' in st.session_state:
                del st.session_state.route_optimized
            if 'conflicts' in st.session_state:
                del st.session_state.conflicts
            st.rerun()
    
    with col_btn3:
        if st.button("🗑️ Tout effacer", use_container_width=True):
            st.session_state.livraisons = []
            st.session_state.depot = None
            if 'route_optimized' in st.session_state:
                del st.session_state.route_optimized
            if 'conflicts' in st.session_state:
                del st.session_state.conflicts
            st.rerun()
    
    # Affichage des conflits
    if 'conflicts' in st.session_state and st.session_state.conflicts:
        st.error("### ⚠️ CONFLITS DÉTECTÉS")
        for conflict in st.session_state.conflicts:
            st.warning(f"**{conflict['client']}** : {conflict['message']} | Retard : **{conflict['retard']}**")
        st.divider()
    
    # Affichage des résultats optimisés
    if 'route_optimized' in st.session_state and st.session_state.route_optimized:
        st.success("### ✅ ITINÉRAIRE OPTIMAL CALCULÉ")
        
        total_distance = 0
        total_latence = 0
        
        for i, delivery in enumerate(st.session_state.route_optimized):
            total_distance += delivery.get('distance_depuis_precedent', 0)
            
            # En-tête de la livraison
            col_num, col_client, col_edit, col_delete = st.columns([1, 6, 1, 1])
            
            with col_num:
                st.markdown(f"### {i+1}.")
            with col_client:
                creneau_str = ""
                if delivery['creneau_debut'] and delivery['creneau_fin']:
                    creneau_str = f" | 🕐 {delivery['creneau_debut'].strftime('%H:%M')}-{delivery['creneau_fin'].strftime('%H:%M')}"
                elif delivery['creneau_debut']:
                    creneau_str = f" | 🕐 Après {delivery['creneau_debut'].strftime('%H:%M')}"
                elif delivery['creneau_fin']:
                    creneau_str = f" | 🕐 Avant {delivery['creneau_fin'].strftime('%H:%M')}"
                
                st.markdown(f"**{delivery['Client']}** - {delivery['Adresse']}{creneau_str}")
            
            with col_edit:
                if st.button("✏️", key=f"edit_{i}", help="Modifier"):
                    # Trouver l'index dans livraisons
                    for idx, liv in enumerate(st.session_state.livraisons):
                        if liv['Client'] == delivery['Client'] and liv['Adresse'] == delivery['Adresse']:
                            st.session_state.mode_edition = idx
                            st.rerun()
            
            with col_delete:
                if st.button("🗑️", key=f"delete_{i}", help="Supprimer"):
                    # Supprimer de livraisons
                    st.session_state.livraisons = [
                        liv for liv in st.session_state.livraisons 
                        if not (liv['Client'] == delivery['Client'] and liv['Adresse'] == delivery['Adresse'])
                    ]
                    del st.session_state.route_optimized
                    st.rerun()
            
            # Détails de la livraison
            col_info1, col_info2, col_info3, col_info4 = st.columns(4)
            
            with col_info1:
                st.metric("🕐 Arrivée", delivery['heure_arrivee'].strftime('%H:%M'))
            with col_info2:
                manutention = delivery['duree_manutention'] or 10
                st.metric("📦 Manutention", minutes_to_hhmm(manutention))
            with col_info3:
                st.metric("🚗 Trajet", f"{delivery.get('distance_depuis_precedent', 0):.1f} km")
            with col_info4:
                st.metric("⏱️ Temps trajet", minutes_to_hhmm(delivery.get('duree_trajet', 0)))
            
            # Afficher latence si > 15 min
            latence = delivery.get('latence', 0)
            if latence and latence > 15:
                total_latence += latence
                
                st.markdown(f"""
                <div style="background: linear-gradient(90deg, #90EE90 0%, #98FB98 100%); 
                            padding: 15px; 
                            border-radius: 10px; 
                            margin: 10px 0;
                            border-left: 5px solid #32CD32;
                            cursor: pointer;">
                    <b>⏳ TEMPS DE LATENCE : {minutes_to_hhmm(latence)}</b> 
                    <span style="color: #666; font-size: 0.9em;">
                        (Arrivée trop tôt - Attente jusqu'au créneau)
                    </span>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"➕ Ajouter un client pendant cette latence", key=f"add_latence_{i}"):
                    st.session_state.insert_latence = i
                    st.rerun()
            
            if i < len(st.session_state.route_optimized) - 1:
                st.markdown("---")
        
        # Retour au dépôt
        st.markdown("### 🏁 Retour au dépôt")
        last_pos = st.session_state.route_optimized[-1]['coords']
        distance_retour = geodesic(last_pos, st.session_state.depot['coords']).km
        total_distance += distance_retour
        duree_retour = int((distance_retour / 60) * 60)
        
        col_retour1, col_retour2 = st.columns(2)
        with col_retour1:
            st.metric("🚗 Distance retour", f"{distance_retour:.1f} km")
        with col_retour2:
            st.metric("⏱️ Temps retour", minutes_to_hhmm(duree_retour))
        
        st.divider()
        
        # Statistiques
        col_stat1, col_stat2, col_stat3, col_stat4, col_stat5 = st.columns(5)
        with col_stat1:
            st.metric("📏 Distance totale", f"{total_distance:.1f} km")
        with col_stat2:
            duree_totale_route = int((total_distance / 60) * 60)
            st.metric("🚗 Temps de route", minutes_to_hhmm(duree_totale_route))
        with col_stat3:
            temps_manutention = sum(d['duree_manutention'] or 10 for d in st.session_state.route_optimized)
            st.metric("📦 Manutention", minutes_to_hhmm(temps_manutention))
        with col_stat4:
            if total_latence > 0:
                st.metric("⏳ Temps latence", minutes_to_hhmm(total_latence))
            else:
                st.metric("⏳ Temps latence", "—")
        with col_stat5:
            duree_totale = duree_totale_route + temps_manutention + total_latence
            st.metric("⏱️ Durée totale", minutes_to_hhmm(duree_totale))
        
        # Heure de fin estimée
        heure_fin = datetime.strptime(st.session_state.depot['heure_depart'], "%H:%M") + timedelta(minutes=duree_totale)
        st.info(f"🏁 **Retour estimé au dépôt** : **{heure_fin.strftime('%H:%M')}**")
        
        # Export Google Maps
        st.divider()
        
        waypoints = [f"{d['coords'][0]},{d['coords'][1]}" for d in st.session_state.route_optimized]
        depot_coords = st.session_state.depot['coords']
        
        google_url = f"https://www.google.com/maps/dir/?api=1&origin={depot_coords[0]},{depot_coords[1]}&destination={depot_coords[0]},{depot_coords[1]}&waypoints={'|'.join(waypoints)}&travelmode=driving"
        
        col_export1, col_export2 = st.columns(2)
        
        with col_export1:
            st.link_button("🗺️ OUVRIR DANS GOOGLE MAPS", google_url, type="primary", use_container_width=True)
        
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
            st.download_button("📥 Télécharger CSV", csv, "tournee_optimisee.csv", "text/csv", use_container_width=True)
    
    else:
        # Liste simple (non optimisée) avec boutons édition
        st.info("👇 **Vos livraisons** (non optimisées)")
        
        for idx, d in enumerate(st.session_state.livraisons):
            col1, col2, col3 = st.columns([6, 1, 1])
            
            with col1:
                creneau_str = ""
                if d['creneau_debut'] and d['creneau_fin']:
                    creneau_str = f" | 🕐 {d['creneau_debut'].strftime('%H:%M')}-{d['creneau_fin'].strftime('%H:%M')}"
                elif d['creneau_debut']:
                    creneau_str = f" | 🕐 Après {d['creneau_debut'].strftime('%H:%M')}"
                elif d['creneau_fin']:
                    creneau_str = f" | 🕐 Avant {d['creneau_fin'].strftime('%H:%M')}"
                
                st.write(f"**{idx + 1}. {d['Client']}** - {d['Adresse']}{creneau_str}")
            
            with col2:
                if st.button("✏️", key=f"edit_simple_{idx}", help="Modifier"):
                    st.session_state.mode_edition = idx
                    st.rerun()
            
            with col3:
                if st.button("🗑️", key=f"delete_simple_{idx}", help="Supprimer"):
                    st.session_state.livraisons.pop(idx)
                    st.rerun()
        
        st.warning("⚠️ Cliquez sur **OPTIMISER** pour calculer l'itinéraire optimal")

else:
    st.info("👆 Commencez par définir le dépôt et l'heure de départ, puis ajoutez des livraisons")

st.divider()
st.caption("💡 **Suisse** : Vitesse moyenne 60 km/h | NPA ou Ville suffisent pour la géolocalisation")
