import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time as time_module

st.set_page_config(page_title="Tournées 🚚", layout="wide")

st.title("🚚 Optimiseur de Tournées Suisse 🇨🇭")
st.markdown("**Modification individuelle + Champs optimisés NPA/Ville**")

# Base de données NPA Suisse (échantillon - à compléter)
NPA_SUISSE = {
    '1000': 'Lausanne', '1003': 'Lausanne', '1004': 'Lausanne', '1005': 'Lausanne',
    '1200': 'Genève', '1201': 'Genève', '1202': 'Genève', '1203': 'Genève', '1204': 'Genève',
    '1205': 'Genève', '1206': 'Genève', '1207': 'Genève', '1208': 'Genève', '1209': 'Genève',
    '1211': 'Genève', '1212': 'Genève', '1213': 'Genève', '1214': 'Genève', '1215': 'Genève',
    '1216': 'Genève', '1217': 'Genève', '1218': 'Genève', '1219': 'Genève', '1220': 'Genève',
    '1400': 'Yverdon-les-Bains', '1401': 'Yverdon-les-Bains',
    '1800': 'Vevey', '1801': 'Le Mont-Pèlerin', '1802': 'Corseaux',
    '2000': 'Neuchâtel', '2001': 'Neuchâtel', '2002': 'Neuchâtel',
    '2500': 'Biel/Bienne', '2501': 'Biel/Bienne', '2502': 'Biel/Bienne',
    '3000': 'Bern', '3001': 'Bern', '3003': 'Bern', '3004': 'Bern', '3005': 'Bern',
    '3006': 'Bern', '3007': 'Bern', '3008': 'Bern', '3010': 'Bern', '3011': 'Bern',
    '3012': 'Bern', '3013': 'Bern', '3014': 'Bern', '3015': 'Bern',
    '4000': 'Basel', '4001': 'Basel', '4002': 'Basel', '4003': 'Basel', '4051': 'Basel',
    '4052': 'Basel', '4053': 'Basel', '4054': 'Basel', '4055': 'Basel', '4056': 'Basel',
    '4057': 'Basel', '4058': 'Basel',
    '5000': 'Aarau', '5001': 'Aarau',
    '6000': 'Luzern', '6003': 'Luzern', '6004': 'Luzern', '6005': 'Luzern',
    '7000': 'Chur', '7001': 'Chur',
    '8000': 'Zürich', '8001': 'Zürich', '8002': 'Zürich', '8003': 'Zürich', '8004': 'Zürich',
    '8005': 'Zürich', '8006': 'Zürich', '8008': 'Zürich', '8032': 'Zürich', '8037': 'Zürich',
    '8038': 'Zürich', '8041': 'Zürich', '8044': 'Zürich', '8045': 'Zürich', '8046': 'Zürich',
    '8047': 'Zürich', '8048': 'Zürich', '8049': 'Zürich', '8050': 'Zürich', '8051': 'Zürich',
    '8052': 'Zürich', '8053': 'Zürich', '8055': 'Zürich', '8057': 'Zürich',
    '9000': 'St. Gallen', '9001': 'St. Gallen', '9004': 'St. Gallen', '9008': 'St. Gallen',
    '1630': 'Bulle', '1700': 'Fribourg', '1950': 'Sion', '3960': 'Sierre',
    '1870': 'Monthey', '1920': 'Martigny', '1860': 'Aigle'
}

VILLE_NPA = {v: k for k, v in NPA_SUISSE.items()}

# Initialiser
if 'livraisons' not in st.session_state:
    st.session_state.livraisons = []
if 'depot' not in st.session_state:
    st.session_state.depot = None
if 'editing_index' not in st.session_state:
    st.session_state.editing_index = None

geolocator = Nominatim(user_agent="delivery_optimizer_swiss")

# Fonction pour convertir minutes en HH:MM
def minutes_to_hhmm(minutes):
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"

# Fonction pour géocoder une adresse suisse
def geocode_address_swiss(numero, rue, npa, ville):
    try:
        address = f"{numero} {rue}, {npa} {ville}, Suisse"
        location = geolocator.geocode(address, timeout=10)
        if location:
            return (location.latitude, location.longitude)
    except:
        pass
    return None

# Fonction pour vérifier si une heure est dans un créneau
def is_in_time_slot(heure, debut, fin):
    if not debut or not fin:
        return True
    return debut <= heure <= fin

# Fonction pour calculer le temps entre deux heures
def time_diff_minutes(time1, time2):
    dt1 = datetime.combine(datetime.today(), time1)
    dt2 = datetime.combine(datetime.today(), time2)
    return int((dt2 - dt1).total_seconds() / 60)

# Fonction d'optimisation
def optimize_route_with_conflicts(depot_coords, deliveries, heure_depart):
    if not deliveries or not depot_coords:
        return [], []
    
    current_time = datetime.combine(datetime.today(), heure_depart)
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
            travel_time = int((distance / 50) * 60)
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
            travel_time = int((distance / 50) * 60)
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

# ===== SECTION 1 : DÉPÔT =====
st.header("🏭 Point de départ")

if st.session_state.depot is None:
    with st.form("depot_form"):
        col1, col2, col3, col4 = st.columns([1, 2, 1, 2])
        
        with col1:
            depot_numero = st.text_input("N°", placeholder="10")
        with col2:
            depot_rue = st.text_input("Rue", placeholder="Route de Lausanne")
        with col3:
            depot_npa = st.text_input("NPA", placeholder="1008")
        with col4:
            # Auto-complétion ville depuis NPA
            ville_auto = NPA_SUISSE.get(depot_npa, "")
            depot_ville = st.text_input("Ville", value=ville_auto, placeholder="Prilly")
        
        heure_depart = st.time_input("⏰ Heure de départ", value=datetime.strptime("08:00", "%H:%M").time())
        
        if st.form_submit_button("📍 Valider le dépôt", type="primary", use_container_width=True):
            if depot_numero and depot_rue and depot_npa and depot_ville:
                with st.spinner("🔍 Géolocalisation..."):
                    coords = geocode_address_swiss(depot_numero, depot_rue, depot_npa, depot_ville)
                    
                    if coords:
                        st.session_state.depot = {
                            'numero': depot_numero,
                            'rue': depot_rue,
                            'npa': depot_npa,
                            'ville': depot_ville,
                            'coords': coords,
                            'heure_depart': heure_depart
                        }
                        st.success(f"✅ Dépôt : {depot_numero} {depot_rue}, {depot_npa} {depot_ville}")
                        st.rerun()
                    else:
                        st.error("❌ Adresse introuvable. Vérifiez le NPA et la ville.")
            else:
                st.error("⚠️ Remplissez tous les champs")
else:
    depot = st.session_state.depot
    col_info, col_reset = st.columns([4, 1])
    
    with col_info:
        st.info(f"📍 **Dépôt** : {depot['numero']} {depot['rue']}, {depot['npa']} {depot['ville']} | 🕐 Départ : **{depot['heure_depart'].strftime('%H:%M')}**")
    
    with col_reset:
        if st.button("🔄 Modifier", use_container_width=True):
            st.session_state.depot = None
            st.rerun()

st.divider()

# ===== SECTION 2 : AJOUT/MODIFICATION LIVRAISONS =====

if st.session_state.editing_index is not None:
    st.header("✏️ Modifier la livraison")
    
    idx = st.session_state.editing_index
    livraison = st.session_state.livraisons[idx]
    
    with st.form("edit_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            nom = st.text_input("Client", value=livraison['Client'])
            
            col_num, col_rue = st.columns([1, 3])
            with col_num:
                numero = st.text_input("N°", value=livraison['numero'])
            with col_rue:
                rue = st.text_input("Rue", value=livraison['rue'])
            
            col_npa, col_ville = st.columns(2)
            with col_npa:
                npa = st.text_input("NPA", value=livraison['npa'])
            with col_ville:
                ville_auto = NPA_SUISSE.get(npa, livraison['ville'])
                ville = st.text_input("Ville", value=ville_auto)
        
        with col2:
            st.markdown("**Créneau horaire (optionnel)**")
            col_time1, col_time2 = st.columns(2)
            with col_time1:
                creneau_debut = st.time_input("De", value=livraison['creneau_debut'])
            with col_time2:
                creneau_fin = st.time_input("À", value=livraison['creneau_fin'])
            
            duree_manutention = st.number_input("Temps manutention (min)", 
                                               min_value=0, 
                                               value=livraison['duree_manutention'] or 0)
        
        col_save, col_cancel = st.columns(2)
        
        with col_save:
            if st.form_submit_button("💾 Enregistrer", type="primary", use_container_width=True):
                with st.spinner("🔍 Géolocalisation..."):
                    coords = geocode_address_swiss(numero, rue, npa, ville)
                    
                    if coords:
                        st.session_state.livraisons[idx] = {
                            'Client': nom,
                            'numero': numero,
                            'rue': rue,
                            'npa': npa,
                            'ville': ville,
                            'creneau_debut': creneau_debut,
                            'creneau_fin': creneau_fin,
                            'duree_manutention': duree_manutention if duree_manutention > 0 else None,
                            'coords': coords
                        }
                        st.session_state.editing_index = None
                        # Supprimer la route optimisée pour forcer le recalcul
                        if 'route_optimized' in st.session_state:
                            del st.session_state.route_optimized
                        st.success(f"✅ {nom} modifié")
                        st.rerun()
                    else:
                        st.error("❌ Adresse introuvable")
        
        with col_cancel:
            if st.form_submit_button("❌ Annuler", use_container_width=True):
                st.session_state.editing_index = None
                st.rerun()

else:
    st.header("📦 Ajouter une livraison")
    
    with st.form("ajout_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            nom = st.text_input("Client", placeholder="Client A")
            
            col_num, col_rue = st.columns([1, 3])
            with col_num:
                numero = st.text_input("N°", placeholder="5")
            with col_rue:
                rue = st.text_input("Rue", placeholder="Avenue de la Gare")
            
            col_npa, col_ville = st.columns(2)
            with col_npa:
                npa = st.text_input("NPA", placeholder="1003")
            with col_ville:
                ville_auto = NPA_SUISSE.get(npa, "")
                ville = st.text_input("Ville", value=ville_auto, placeholder="Lausanne")
        
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
            if nom and numero and rue and npa and ville:
                with st.spinner("🔍 Géolocalisation..."):
                    time_module.sleep(0.5)
                    coords = geocode_address_swiss(numero, rue, npa, ville)
                    
                    if coords:
                        st.session_state.livraisons.append({
                            'Client': nom,
                            'numero': numero,
                            'rue': rue,
                            'npa': npa,
                            'ville': ville,
                            'creneau_debut': creneau_debut,
                            'creneau_fin': creneau_fin,
                            'duree_manutention': duree_manutention if duree_manutention > 0 else None,
                            'coords': coords
                        })
                        # Supprimer la route optimisée pour forcer le recalcul
                        if 'route_optimized' in st.session_state:
                            del st.session_state.route_optimized
                        st.success(f"✅ {nom} ajouté")
                        st.rerun()
                    else:
                        st.error(f"❌ Adresse introuvable : {numero} {rue}, {npa} {ville}")
            else:
                st.error("⚠️ Remplissez tous les champs obligatoires")

st.divider()

# ===== SECTION 3 : LISTE ET OPTIMISATION =====
st.header(f"🗺️ Tournée ({len(st.session_state.livraisons)} livraisons)")

if st.session_state.livraisons:
    
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        if st.button("🚀 OPTIMISER LA TOURNÉE", type="primary", use_container_width=True):
            if not st.session_state.depot:
                st.error("❌ Définissez d'abord le dépôt !")
            else:
                with st.spinner("⏳ Optimisation en cours..."):
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
        if st.button("🗑️ Tout effacer", use_container_width=True):
            st.session_state.livraisons = []
            st.session_state.depot = None
            st.session_state.editing_index = None
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
        
        route_data = []
        total_distance = 0
        total_latence = 0
        
        for i, delivery in enumerate(st.session_state.route_optimized, 1):
            total_distance += delivery.get('distance_depuis_precedent', 0)
            
            creneau_str = ""
            if delivery['creneau_debut'] and delivery['creneau_fin']:
                creneau_str = f"{delivery['creneau_debut'].strftime('%H:%M')}-{delivery['creneau_fin'].strftime('%H:%M')}"
            elif delivery['creneau_debut']:
                creneau_str = f"Après {delivery['creneau_debut'].strftime('%H:%M')}"
            elif delivery['creneau_fin']:
                creneau_str = f"Avant {delivery['creneau_fin'].strftime('%H:%M')}"
            else:
                creneau_str = "—"
            
            manutention = delivery['duree_manutention'] or 10
            latence = delivery.get('latence', 0)
            if latence:
                total_latence += latence
            
            latence_display = ""
            if latence and latence > 15:
                latence_display = f"⏳ {minutes_to_hhmm(latence)}"
            
            route_data.append({
                'N°': i,
                'Client': delivery['Client'],
                'Adresse': f"{delivery['numero']} {delivery['rue']}, {delivery['npa']} {delivery['ville']}",
                'Créneau': creneau_str,
                'Arrivée': delivery['heure_arrivee'].strftime('%H:%M'),
                'Latence': latence_display if latence_display else "—",
                'Manut.': minutes_to_hhmm(manutention),
                'Distance': f"{delivery.get('distance_depuis_precedent', 0):.1f} km",
                'Trajet': minutes_to_hhmm(delivery.get('duree_trajet', 0))
            })
        
        # Retour au dépôt
        last_pos = st.session_state.route_optimized[-1]['coords']
        distance_retour = geodesic(last_pos, st.session_state.depot['coords']).km
        total_distance += distance_retour
        duree_retour = int((distance_retour / 50) * 60)
        
        df = pd.DataFrame(route_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Statistiques
        col_stat1, col_stat2, col_stat3, col_stat4, col_stat5 = st.columns(5)
        with col_stat1:
            st.metric("📏 Distance totale", f"{total_distance:.1f} km")
        with col_stat2:
            duree_totale_route = int((total_distance / 50) * 60)
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
        heure_debut = datetime.combine(datetime.today(), st.session_state.depot['heure_depart'])
        heure_fin = heure_debut + timedelta(minutes=duree_totale)
        st.info(f"🏁 **Retour estimé au dépôt** : {heure_fin.strftime('%H:%M')}")
        
        # Export Google Maps
        st.divider()
        
        waypoints = [f"{d['coords'][0]},{d['coords'][1]}" for d in st.session_state.route_optimized]
        depot_coords = st.session_state.depot['coords']
        
        google_url = f"https://www.google.com/maps/dir/?api=1&origin={depot_coords[0]},{depot_coords[1]}&destination={depot_coords[0]},{depot_coords[1]}&waypoints={'|'.join(waypoints)}&travelmode=driving"
        
        col_export1, col_export2 = st.columns(2)
        
        with col_export1:
            st.link_button("🗺️ OUVRIR DANS GOOGLE MAPS", google_url, type="primary", use_container_width=True)
        
        with col_export2:
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Télécharger CSV", csv, "tournee_optimisee.csv", "text/csv", use_container_width=True)
        
    else:
        # Affichage liste simple avec boutons modification/suppression
        st.markdown("### 📋 Liste des livraisons (non optimisée)")
        
        for idx, livraison in enumerate(st.session_state.livraisons):
            col1, col2, col3 = st.columns([6, 1, 1])
            
            with col1:
                creneau_display = ""
                if livraison['creneau_debut'] and livraison['creneau_fin']:
                    creneau_display = f"🕐 {livraison['creneau_debut'].strftime('%H:%M')}-{livraison['creneau_fin'].strftime('%H:%M')}"
                elif livraison['creneau_debut']:
                    creneau_display = f"🕐 Après {livraison['creneau_debut'].strftime('%H:%M')}"
                elif livraison['creneau_fin']:
                    creneau_display = f"🕐 Avant {livraison['creneau_fin'].strftime('%H:%M')}"
                
                manut_display = f"⏱️ {livraison['duree_manutention'] or 10} min"
                
                st.markdown(f"""
                **{livraison['Client']}** - {livraison['numero']} {livraison['rue']}, {livraison['npa']} {livraison['ville']}  
                {creneau_display} | {manut_display}
                """)
            
            with col2:
                if st.button("✏️", key=f"edit_{idx}", use_container_width=True):
                    st.session_state.editing_index = idx
                    st.rerun()
            
            with col3:
                if st.button("🗑️", key=f"delete_{idx}", use_container_width=True):
                    st.session_state.livraisons.pop(idx)
                    if 'route_optimized' in st.session_state:
                        del st.session_state.route_optimized
                    st.rerun()
            
            st.divider()
        
        st.warning("⚠️ Cliquez sur **OPTIMISER** pour calculer l'itinéraire optimal")

else:
    st.info("👆 Commencez par définir le dépôt, puis ajoutez des livraisons")

st.divider()
st.caption("💡 **Astuce** : Vous pouvez modifier ou supprimer chaque livraison individuellement. Les créneaux et la manutention sont optionnels.")
