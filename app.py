import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time as time_module

st.set_page_config(page_title="Tournées 🚚", layout="wide")

st.title("🚚 Optimiseur de Tournées Intelligent")
st.markdown("**Créneaux horaires + Temps de manutention personnalisable**")

# Initialiser
if 'livraisons' not in st.session_state:
    st.session_state.livraisons = []
if 'depot' not in st.session_state:
    st.session_state.depot = None

geolocator = Nominatim(user_agent="delivery_optimizer_v3")

# Fonction pour géocoder une adresse
def geocode_address(address):
    try:
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

# Fonction d'optimisation avancée
def optimize_route_with_slots(depot_coords, deliveries, heure_depart="08:00"):
    if not deliveries or not depot_coords:
        return []
    
    # Convertir heure de départ
    current_time = datetime.strptime(heure_depart, "%H:%M")
    current_pos = depot_coords
    
    # Séparer les livraisons avec/sans contraintes horaires
    with_slots = [d for d in deliveries if d['creneau_debut'] or d['creneau_fin']]
    without_slots = [d for d in deliveries if not d['creneau_debut'] and not d['creneau_fin']]
    
    route = []
    remaining_with_slots = with_slots.copy()
    remaining_without_slots = without_slots.copy()
    
    # Algorithme hybride
    while remaining_with_slots or remaining_without_slots:
        best_delivery = None
        best_distance = float('inf')
        
        # Prioriser les créneaux contraints
        for delivery in remaining_with_slots:
            distance = geodesic(current_pos, delivery['coords']).km
            travel_time = int((distance / 50) * 60)  # Vitesse 50 km/h
            arrival_time = (current_time + timedelta(minutes=travel_time)).time()
            
            # Vérifier si on peut arriver dans le créneau
            debut = delivery['creneau_debut']
            fin = delivery['creneau_fin']
            
            if debut and arrival_time < debut:
                # Trop tôt, attendre
                wait_time = (datetime.combine(datetime.today(), debut) - 
                            datetime.combine(datetime.today(), arrival_time)).seconds // 60
                if wait_time < 60:  # Max 1h d'attente
                    if distance < best_distance:
                        best_distance = distance
                        best_delivery = delivery
            elif is_in_time_slot(arrival_time, debut, fin):
                if distance < best_distance:
                    best_distance = distance
                    best_delivery = delivery
        
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
            travel_time = int((distance / 50) * 60)
            arrival_time = current_time + timedelta(minutes=travel_time)
            
            # Attendre si trop tôt
            if best_delivery['creneau_debut']:
                debut_dt = datetime.combine(datetime.today(), best_delivery['creneau_debut'])
                if arrival_time < debut_dt:
                    arrival_time = debut_dt
            
            best_delivery['heure_arrivee'] = arrival_time.time()
            best_delivery['distance_depuis_precedent'] = distance
            best_delivery['duree_trajet'] = travel_time
            
            route.append(best_delivery)
            
            # Mise à jour pour prochaine itération
            current_pos = best_delivery['coords']
            manutention = best_delivery['duree_manutention'] or 10
            current_time = arrival_time + timedelta(minutes=manutention)
            
            if best_delivery in remaining_with_slots:
                remaining_with_slots.remove(best_delivery)
            if best_delivery in remaining_without_slots:
                remaining_without_slots.remove(best_delivery)
        else:
            break
    
    return route

# ===== SECTION 1 : DÉPÔT =====
st.header("🏭 Point de départ")

col_depot1, col_depot2, col_depot3 = st.columns([3, 2, 1])

with col_depot1:
    depot_address = st.text_input("Adresse du dépôt", placeholder="Ex: 10 Rue de Paris, 75001 Paris")

with col_depot2:
    heure_depart = st.time_input("Heure de départ", value=datetime.strptime("08:00", "%H:%M").time())

with col_depot3:
    if st.button("📍 Valider", type="primary"):
        if depot_address:
            with st.spinner("🔍 Géolocalisation..."):
                coords = geocode_address(depot_address)
                if coords:
                    st.session_state.depot = {
                        'adresse': depot_address,
                        'coords': coords,
                        'heure_depart': heure_depart.strftime("%H:%M")
                    }
                    st.success(f"✅ Dépôt : {depot_address}")
                    st.rerun()
                else:
                    st.error("❌ Adresse introuvable")

if st.session_state.depot:
    st.info(f"📍 **Dépôt** : {st.session_state.depot['adresse']} | 🕐 Départ : {st.session_state.depot['heure_depart']}")

st.divider()

# ===== SECTION 2 : AJOUT LIVRAISONS =====
st.header("📦 Ajouter une livraison")

with st.form("ajout_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    
    with col1:
        nom = st.text_input("Client", placeholder="Ex: Client A")
        adresse = st.text_input("Adresse complète", placeholder="Ex: 5 Rue Victor Hugo, 69002 Lyon")
    
    with col2:
        st.markdown("**Créneau horaire (optionnel)**")
        col_time1, col_time2 = st.columns(2)
        with col_time1:
            creneau_debut = st.time_input("De", value=None, key="debut", help="Laissez vide si pas de contrainte")
        with col_time2:
            creneau_fin = st.time_input("À", value=None, key="fin", help="Laissez vide si pas de contrainte")
        
        duree_manutention = st.number_input("Temps manutention (min)", min_value=0, value=0, 
                                           help="Laissez à 0 pour 10 min par défaut")
    
    if st.form_submit_button("➕ Ajouter la livraison", type="primary", use_container_width=True):
        if nom and adresse:
            with st.spinner("🔍 Géolocalisation..."):
                time_module.sleep(0.5)
                coords = geocode_address(adresse)
                
                if coords:
                    st.session_state.livraisons.append({
                        'Client': nom,
                        'Adresse': adresse,
                        'creneau_debut': creneau_debut,
                        'creneau_fin': creneau_fin,
                        'duree_manutention': duree_manutention if duree_manutention > 0 else None,
                        'coords': coords
                    })
                    st.success(f"✅ {nom} ajouté")
                    st.rerun()
                else:
                    st.error(f"❌ Adresse introuvable : {adresse}")
        else:
            st.error("⚠️ Remplissez au moins le nom et l'adresse")

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
                    route = optimize_route_with_slots(
                        st.session_state.depot['coords'],
                        st.session_state.livraisons,
                        st.session_state.depot['heure_depart']
                    )
                    st.session_state.route_optimized = route
                    st.success("✅ Tournée optimisée !")
                    st.rerun()
    
    with col_btn2:
        if st.button("🗑️ Tout effacer", use_container_width=True):
            st.session_state.livraisons = []
            st.session_state.depot = None
            if 'route_optimized' in st.session_state:
                del st.session_state.route_optimized
            st.rerun()
    
    # Affichage des résultats optimisés
    if 'route_optimized' in st.session_state and st.session_state.route_optimized:
        st.success("### ✅ ITINÉRAIRE OPTIMAL CALCULÉ")
        
        route_data = []
        total_distance = 0
        
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
            
            route_data.append({
                'N°': i,
                'Client': delivery['Client'],
                'Adresse': delivery['Adresse'],
                'Créneau': creneau_str,
                'Arrivée': delivery['heure_arrivee'].strftime('%H:%M'),
                'Manut.': f"{manutention} min",
                'Distance': f"{delivery.get('distance_depuis_precedent', 0):.1f} km",
                'Trajet': f"{delivery.get('duree_trajet', 0)} min"
            })
        
        # Retour au dépôt
        last_pos = st.session_state.route_optimized[-1]['coords']
        distance_retour = geodesic(last_pos, st.session_state.depot['coords']).km
        total_distance += distance_retour
        
        df = pd.DataFrame(route_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Statistiques
        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
        with col_stat1:
            st.metric("📏 Distance totale", f"{total_distance:.1f} km")
        with col_stat2:
            duree_totale = int((total_distance / 50) * 60)
            st.metric("🚗 Temps de route", f"{duree_totale} min")
        with col_stat3:
            temps_manutention = sum(d['duree_manutention'] or 10 for d in st.session_state.route_optimized)
            st.metric("📦 Temps manutention", f"{temps_manutention} min")
        with col_stat4:
            st.metric("⏱️ Durée totale", f"{duree_totale + temps_manutention} min")
        
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
        # Affichage liste simple (non optimisée)
        df_simple = pd.DataFrame([{
            'Client': d['Client'],
            'Adresse': d['Adresse'],
            'Créneau': f"{d['creneau_debut'].strftime('%H:%M') if d['creneau_debut'] else '—'} - {d['creneau_fin'].strftime('%H:%M') if d['creneau_fin'] else '—'}",
            'Manutention': f"{d['duree_manutention'] or 10} min"
        } for d in st.session_state.livraisons])
        
        st.dataframe(df_simple, use_container_width=True, hide_index=True)
        st.warning("⚠️ Cliquez sur **OPTIMISER** pour calculer l'itinéraire optimal")

else:
    st.info("👆 Commencez par définir le dépôt, puis ajoutez des livraisons")

st.divider()
st.caption("💡 **Astuce** : Laissez les créneaux vides pour une optimisation totale. La manutention par défaut est de 10 minutes.")
