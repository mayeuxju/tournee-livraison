import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time as time_module

st.set_page_config(page_title="Tournées 🚚", layout="wide")

st.title("🚚 Optimiseur de Tournées - Suisse")
st.markdown("**Modification individuelle + Adresses optimisées**")

# Initialiser
if 'livraisons' not in st.session_state:
    st.session_state.livraisons = []
if 'depot' not in st.session_state:
    st.session_state.depot = None
if 'editing_index' not in st.session_state:
    st.session_state.editing_index = None

geolocator = Nominatim(user_agent="delivery_optimizer_swiss_v1")

# Base de données simplifiée NPA Suisse (à enrichir)
NPA_SUISSE = {
    "1000": "Lausanne", "1003": "Lausanne", "1004": "Lausanne",
    "1200": "Genève", "1201": "Genève", "1202": "Genève",
    "1400": "Yverdon-les-Bains", "1630": "Bulle",
    "1700": "Fribourg", "1800": "Vevey",
    "2000": "Neuchâtel", "2300": "La Chaux-de-Fonds",
    "3000": "Berne", "3001": "Berne", "3011": "Berne",
    "4000": "Bâle", "4001": "Bâle",
    "6000": "Lucerne", "6900": "Lugano",
    "8000": "Zurich", "8001": "Zurich", "8002": "Zurich",
    "9000": "Saint-Gall",
}

# Fonction pour obtenir la ville depuis le NPA
def get_ville_from_npa(npa):
    return NPA_SUISSE.get(str(npa), "")

# Fonction pour convertir minutes en HH:MM
def minutes_to_hhmm(minutes):
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"

# Fonction pour géocoder une adresse
def geocode_address(numero, rue, npa, ville, pays="Suisse"):
    adresse_complete = f"{numero} {rue}, {npa} {ville}, {pays}"
    try:
        location = geolocator.geocode(adresse_complete, timeout=10)
        if location:
            return (location.latitude, location.longitude), adresse_complete
    except:
        pass
    return None, adresse_complete

# Fonction pour calculer le temps entre deux heures
def time_diff_minutes(time1, time2):
    dt1 = datetime.combine(datetime.today(), time1)
    dt2 = datetime.combine(datetime.today(), time2)
    return int((dt2 - dt1).total_seconds() / 60)

# Fonction d'optimisation
def optimize_route_with_conflicts(depot_coords, deliveries, heure_depart):
    if not deliveries or not depot_coords:
        return [], []
    
    # Convertir heure de départ
    current_time = datetime.combine(datetime.today(), heure_depart)
    current_pos = depot_coords
    
    # Séparer les livraisons avec/sans contraintes horaires
    with_slots = [d for d in deliveries if d['creneau_debut'] or d['creneau_fin']]
    without_slots = [d for d in deliveries if not d['creneau_debut'] and not d['creneau_fin']]
    
    route = []
    conflicts = []
    remaining_with_slots = with_slots.copy()
    remaining_without_slots = without_slots.copy()
    
    # Algorithme hybride
    while remaining_with_slots or remaining_without_slots:
        best_delivery = None
        best_distance = float('inf')
        has_conflict = False
        
        # Prioriser les créneaux contraints
        for delivery in remaining_with_slots:
            distance = geodesic(current_pos, delivery['coords']).km
            travel_time = int((distance / 60) * 60)  # Vitesse 60 km/h (Suisse)
            arrival_time = (current_time + timedelta(minutes=travel_time)).time()
            
            # Vérifier si on peut arriver dans le créneau
            debut = delivery['creneau_debut']
            fin = delivery['creneau_fin']
            
            # Détecter les conflits
            conflict_info = None
            
            if fin and arrival_time > fin:
                # Arrivée trop tard
                minutes_late = time_diff_minutes(fin, arrival_time)
                conflict_info = f"⚠️ CONFLIT : Arrivée à {arrival_time.strftime('%H:%M')}, créneau fermé à {fin.strftime('%H:%M')} (retard: {minutes_late} min)"
                has_conflict = True
            
            if debut and arrival_time < debut:
                # Trop tôt, calculer temps d'attente
                wait_time = time_diff_minutes(arrival_time, debut)
                if wait_time > 120:  # Plus de 2h d'attente
                    conflict_info = f"⚠️ CONFLIT : Arrivée à {arrival_time.strftime('%H:%M')}, créneau commence à {debut.strftime('%H:%M')} (attente: {minutes_to_hhmm(wait_time)})"
                    has_conflict = True
                else:
                    # Attendre
                    arrival_time = debut
            
            if not has_conflict or not best_delivery:
                if distance < best_distance:
                    best_distance = distance
                    best_delivery = delivery
                    if conflict_info:
                        delivery['conflict'] = conflict_info
        
        # Si aucune contrainte respectée, prendre le plus proche sans créneau
        if not best_delivery and remaining_without_slots:
            best_delivery = min(remaining_without_slots, 
                              key=lambda d: geodesic(current_pos, d['coords']).km)
        
        # Si toujours rien, forcer une livraison avec créneau
        if not best_delivery and remaining_with_slots:
            best_delivery = min(remaining_with_slots,
                              key=lambda d: geodesic(current_pos, d['coords']).km)
        
        if best_delivery:
            # Calculer l'heure d'arrivée réelle
            distance = geodesic(current_pos, best_delivery['coords']).km
            travel_time = int((distance / 60) * 60)
            arrival_time_dt = current_time + timedelta(minutes=travel_time)
            arrival_time = arrival_time_dt.time()
            
            # Calculer temps de latence
            latence = 0
            if best_delivery['creneau_debut']:
                debut_dt = datetime.combine(datetime.today(), best_delivery['creneau_debut'])
                if arrival_time_dt < debut_dt:
                    latence = time_diff_minutes(arrival_time, best_delivery['creneau_debut'])
                    arrival_time_dt = debut_dt
                    arrival_time = best_delivery['creneau_debut']
            
            # Vérifier conflit final
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
            
            # Mise à jour pour prochaine itération
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

if st.session_state.depot:
    col_info1, col_info2, col_info3 = st.columns([3, 2, 1])
    
    with col_info1:
        st.info(f"📍 **Dépôt** : {st.session_state.depot['adresse']}")
    
    with col_info2:
        st.info(f"🕐 **Départ** : {st.session_state.depot['heure_depart'].strftime('%H:%M')}")
    
    with col_info3:
        if st.button("✏️ Modifier", key="edit_depot"):
            st.session_state.depot = None
            st.rerun()
else:
    with st.form("depot_form"):
        st.subheader("Définir le dépôt")
        
        col1, col2 = st.columns(2)
        
        with col1:
            depot_numero = st.text_input("N°", placeholder="Ex: 15")
            depot_rue = st.text_input("Rue", placeholder="Ex: Avenue de la Gare")
        
        with col2:
            depot_npa = st.text_input("NPA", placeholder="Ex: 1003", max_chars=4)
            
            # Auto-complétion ville
            ville_auto = get_ville_from_npa(depot_npa) if depot_npa else ""
            depot_ville = st.text_input("Ville", value=ville_auto, placeholder="Ex: Lausanne")
        
        heure_depart = st.time_input("🕐 Heure de départ", value=datetime.strptime("08:00", "%H:%M").time())
        
        if st.form_submit_button("📍 Valider le dépôt", type="primary", use_container_width=True):
            if depot_numero and depot_rue and depot_npa and depot_ville:
                with st.spinner("🔍 Géolocalisation du dépôt..."):
                    coords, adresse = geocode_address(depot_numero, depot_rue, depot_npa, depot_ville)
                    
                    if coords:
                        st.session_state.depot = {
                            'adresse': adresse,
                            'coords': coords,
                            'heure_depart': heure_depart
                        }
                        st.success(f"✅ Dépôt enregistré : {adresse}")
                        st.rerun()
                    else:
                        st.error(f"❌ Adresse introuvable : {adresse}")
            else:
                st.error("⚠️ Remplissez tous les champs")

st.divider()

# ===== SECTION 2 : AJOUT/MODIFICATION LIVRAISONS =====
if st.session_state.editing_index is not None:
    st.header("✏️ Modifier une livraison")
    
    delivery = st.session_state.livraisons[st.session_state.editing_index]
    
    with st.form("edit_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            nom = st.text_input("Client", value=delivery['Client'])
            numero = st.text_input("N°", value=delivery['numero'])
            rue = st.text_input("Rue", value=delivery['rue'])
        
        with col2:
            npa = st.text_input("NPA", value=delivery['npa'], max_chars=4)
            ville_auto = get_ville_from_npa(npa) if npa else delivery['ville']
            ville = st.text_input("Ville", value=ville_auto)
        
        st.markdown("**Créneau horaire (optionnel)**")
        col_time1, col_time2, col_time3 = st.columns(3)
        
        with col_time1:
            creneau_debut = st.time_input("De", value=delivery['creneau_debut'], key="edit_debut")
        with col_time2:
            creneau_fin = st.time_input("À", value=delivery['creneau_fin'], key="edit_fin")
        with col_time3:
            duree_manutention = st.number_input("Manutention (min)", min_value=0, 
                                               value=delivery['duree_manutention'] or 0)
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.form_submit_button("💾 Enregistrer", type="primary", use_container_width=True):
                if nom and numero and rue and npa and ville:
                    with st.spinner("🔍 Mise à jour..."):
                        coords, adresse = geocode_address(numero, rue, npa, ville)
                        
                        if coords:
                            st.session_state.livraisons[st.session_state.editing_index] = {
                                'Client': nom,
                                'numero': numero,
                                'rue': rue,
                                'npa': npa,
                                'ville': ville,
                                'Adresse': adresse,
                                'creneau_debut': creneau_debut,
                                'creneau_fin': creneau_fin,
                                'duree_manutention': duree_manutention if duree_manutention > 0 else None,
                                'coords': coords
                            }
                            st.session_state.editing_index = None
                            # Supprimer la tournée optimisée
                            if 'route_optimized' in st.session_state:
                                del st.session_state.route_optimized
                            if 'conflicts' in st.session_state:
                                del st.session_state.conflicts
                            st.success("✅ Livraison modifiée")
                            st.rerun()
                        else:
                            st.error(f"❌ Adresse introuvable : {numero} {rue}, {npa} {ville}")
                else:
                    st.error("⚠️ Remplissez tous les champs")
        
        with col_btn2:
            if st.form_submit_button("❌ Annuler", use_container_width=True):
                st.session_state.editing_index = None
                st.rerun()
    
else:
    st.header("📦 Ajouter une livraison")
    
    with st.form("ajout_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            nom = st.text_input("Client", placeholder="Ex: Restaurant du Port")
            numero = st.text_input("N°", placeholder="Ex: 25")
            rue = st.text_input("Rue", placeholder="Ex: Rue de Lausanne")
        
        with col2:
            npa = st.text_input("NPA", placeholder="Ex: 1003", max_chars=4)
            
            # Auto-complétion ville
            ville_auto = get_ville_from_npa(npa) if npa else ""
            ville = st.text_input("Ville", value=ville_auto, placeholder="Ex: Lausanne")
        
        st.markdown("**Créneau horaire (optionnel)**")
        col_time1, col_time2, col_time3 = st.columns(3)
        
        with col_time1:
            creneau_debut = st.time_input("De", value=None, key="debut", help="Laissez vide si pas de contrainte")
        with col_time2:
            creneau_fin = st.time_input("À", value=None, key="fin", help="Laissez vide si pas de contrainte")
        with col_time3:
            duree_manutention = st.number_input("Manutention (min)", min_value=0, value=0, 
                                               help="Laissez à 0 pour 10 min par défaut")
        
        if st.form_submit_button("➕ Ajouter la livraison", type="primary", use_container_width=True):
            if nom and numero and rue and npa and ville:
                with st.spinner("🔍 Géolocalisation..."):
                    time_module.sleep(0.5)
                    coords, adresse = geocode_address(numero, rue, npa, ville)
                    
                    if coords:
                        st.session_state.livraisons.append({
                            'Client': nom,
                            'numero': numero,
                            'rue': rue,
                            'npa': npa,
                            'ville': ville,
                            'Adresse': adresse,
                            'creneau_debut': creneau_debut,
                            'creneau_fin': creneau_fin,
                            'duree_manutention': duree_manutention if duree_manutention > 0 else None,
                            'coords': coords
                        })
                        # Supprimer la tournée optimisée si elle existe
                        if 'route_optimized' in st.session_state:
                            del st.session_state.route_optimized
                        if 'conflicts' in st.session_state:
                            del st.session_state.conflicts
                        st.success(f"✅ {nom} ajouté")
                        st.rerun()
                    else:
                        st.error(f"❌ Adresse introuvable : {numero} {rue}, {npa} {ville}")
            else:
                st.error("⚠️ Remplissez au moins : Client, N°, Rue, NPA, Ville")

st.divider()

# ===== SECTION 3 : LISTE ET OPTIMISATION =====
st.header(f"🗺️ Tournée ({len(st.session_state.livraisons)} livraisons)")

if st.session_state.livraisons:
    
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        if st.button("🚀 OPTIMISER LA TOURNÉE", type="primary", use_container_width=True, disabled=not st.session_state.depot):
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
            
            # Afficher latence uniquement si > 15 min
            latence_display = ""
            if latence and latence > 15:
                latence_display = f"⏳ {minutes_to_hhmm(latence)}"
            
            route_data.append({
                'N°': i,
                'Client': delivery['Client'],
                'Adresse': delivery['Adresse'],
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
        duree_retour = int((distance_retour / 60) * 60)
        
        df = pd.DataFrame(route_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
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
        heure_fin = datetime.combine(datetime.today(), st.session_state.depot['heure_depart']) + timedelta(minutes=duree_totale)
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
        # Affichage liste simple (non optimisée) avec actions
        st.markdown("### 📋 Livraisons non optimisées")
        
        for i, delivery in enumerate(st.session_state.livraisons):
            col1, col2, col3 = st.columns([5, 1, 1])
            
            with col1:
                creneau = ""
                if delivery['creneau_debut'] and delivery['creneau_fin']:
                    creneau = f" | 🕐 {delivery['creneau_debut'].strftime('%H:%M')}-{delivery['creneau_fin'].strftime('%H:%M')}"
                elif delivery['creneau_debut']:
                    creneau = f" | 🕐 Après {delivery['creneau_debut'].strftime('%H:%M')}"
                elif delivery['creneau_fin']:
                    creneau = f" | 🕐 Avant {delivery['creneau_fin'].strftime('%H:%M')}"
                
                manut = f" | ⏱️ {minutes_to_hhmm(delivery['duree_manutention'] or 10)}"
                
                st.write(f"**{i+1}. {delivery['Client']}**  \n{delivery['Adresse']}{creneau}{manut}")
            
            with col2:
                if st.button("✏️", key=f"edit_{i}", help="Modifier", use_container_width=True):
                    st.session_state.editing_index = i
                    st.rerun()
            
            with col3:
                if st.button("🗑️", key=f"delete_{i}", help="Supprimer", use_container_width=True):
                    st.session_state.livraisons.pop(i)
                    if 'route_optimized' in st.session_state:
                        del st.session_state.route_optimized
                    if 'conflicts' in st.session_state:
                        del st.session_state.conflicts
                    st.rerun()
            
            st.divider()
        
        if not st.session_state.depot:
            st.warning("⚠️ Définissez d'abord le **dépôt** pour pouvoir optimiser")
        else:
            st.info("👆 Cliquez sur **OPTIMISER** pour calculer l'itinéraire optimal")

else:
    st.info("👆 Commencez par définir le dépôt, puis ajoutez des livraisons")

st.divider()
st.caption("💡 **Astuce** : Tapez le NPA et la ville se remplit automatiquement. Vous pouvez la modifier si nécessaire.")
