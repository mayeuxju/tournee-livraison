import streamlit as st
import pandas as pd
from datetime import datetime
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time

st.set_page_config(page_title="Tournées 🚚", layout="wide")

st.title("🚚 Optimiseur de Tournées Automatique")
st.markdown("**L'application calcule automatiquement l'ordre optimal des livraisons**")

# Initialiser
if 'livraisons' not in st.session_state:
    st.session_state.livraisons = []
if 'depot' not in st.session_state:
    st.session_state.depot = None

geolocator = Nominatim(user_agent="delivery_optimizer_v2")

# Fonction pour géocoder une adresse
def geocode_address(address):
    try:
        location = geolocator.geocode(address, timeout=10)
        if location:
            return (location.latitude, location.longitude)
    except:
        pass
    return None

# Fonction d'optimisation (algorithme du plus proche voisin)
def optimize_route(depot_coords, deliveries):
    if not deliveries or not depot_coords:
        return []
    
    route = []
    remaining = deliveries.copy()
    current_pos = depot_coords
    
    # Algorithme du plus proche voisin
    while remaining:
        # Trouver la livraison la plus proche
        closest = min(remaining, key=lambda d: geodesic(current_pos, d['coords']).km)
        route.append(closest)
        current_pos = closest['coords']
        remaining.remove(closest)
    
    return route

# ===== SECTION 1 : DÉPÔT =====
st.header("🏭 Point de départ (dépôt)")

col_depot1, col_depot2 = st.columns([3, 1])

with col_depot1:
    depot_address = st.text_input("Adresse du dépôt", placeholder="Ex: 10 Rue de Paris, 75001 Paris")

with col_depot2:
    if st.button("📍 Définir dépôt", type="primary"):
        if depot_address:
            with st.spinner("🔍 Géolocalisation..."):
                coords = geocode_address(depot_address)
                if coords:
                    st.session_state.depot = {
                        'adresse': depot_address,
                        'coords': coords
                    }
                    st.success(f"✅ Dépôt enregistré : {depot_address}")
                    st.rerun()
                else:
                    st.error("❌ Adresse introuvable")

if st.session_state.depot:
    st.info(f"📍 **Dépôt actuel** : {st.session_state.depot['adresse']}")

st.divider()

# ===== SECTION 2 : AJOUT LIVRAISONS =====
st.header("📦 Ajouter des livraisons")

with st.form("ajout_form", clear_on_submit=True):
    col1, col2, col3 = st.columns([2, 3, 1])
    
    with col1:
        nom = st.text_input("Client", placeholder="Ex: Client A")
    
    with col2:
        adresse = st.text_input("Adresse", placeholder="Ex: 5 Rue Victor Hugo, 69002 Lyon")
    
    with col3:
        heure_fixe = st.text_input("Heure (opt.)", placeholder="09:30", help="Laissez vide pour auto")
    
    if st.form_submit_button("➕ Ajouter", type="primary", use_container_width=True):
        if nom and adresse:
            with st.spinner("🔍 Géolocalisation..."):
                time.sleep(0.5)  # Anti-spam
                coords = geocode_address(adresse)
                
                if coords:
                    st.session_state.livraisons.append({
                        'Client': nom,
                        'Adresse': adresse,
                        'Heure_imposee': heure_fixe if heure_fixe else None,
                        'coords': coords
                    })
                    st.success(f"✅ {nom} ajouté ({coords[0]:.4f}, {coords[1]:.4f})")
                    st.rerun()
                else:
                    st.error(f"❌ Impossible de trouver : {adresse}")
        else:
            st.error("⚠️ Remplissez au moins le nom et l'adresse")

st.divider()

# ===== SECTION 3 : OPTIMISATION =====
st.header(f"🗺️ Tournée optimisée ({len(st.session_state.livraisons)} livraisons)")

if st.session_state.livraisons:
    
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    
    with col_btn1:
        if st.button("🚀 OPTIMISER", type="primary", use_container_width=True):
            if not st.session_state.depot:
                st.error("❌ Définissez d'abord le dépôt !")
            else:
                with st.spinner("⏳ Calcul de l'itinéraire optimal..."):
                    # Séparer les livraisons avec/sans heure imposée
                    with_time = [d for d in st.session_state.livraisons if d['Heure_imposee']]
                    without_time = [d for d in st.session_state.livraisons if not d['Heure_imposee']]
                    
                    # Trier celles avec heure
                    with_time.sort(key=lambda x: x['Heure_imposee'])
                    
                    # Optimiser celles sans heure
                    optimized_without = optimize_route(st.session_state.depot['coords'], without_time)
                    
                    # Combiner (priorité aux heures imposées)
                    st.session_state.route_optimized = with_time + optimized_without
                    st.success("✅ Tournée optimisée !")
                    st.rerun()
    
    with col_btn2:
        if st.button("🗑️ Tout effacer", use_container_width=True):
            st.session_state.livraisons = []
            st.session_state.depot = None
            if 'route_optimized' in st.session_state:
                del st.session_state.route_optimized
            st.rerun()
    
    # Affichage des résultats
    if 'route_optimized' in st.session_state and st.session_state.route_optimized:
        st.success("### ✅ ITINÉRAIRE OPTIMAL")
        
        # Calculer distances et durées
        route_data = []
        total_distance = 0
        current_pos = st.session_state.depot['coords']
        heure_actuelle = datetime.strptime("08:00", "%H:%M")
        
        for i, delivery in enumerate(st.session_state.route_optimized, 1):
            distance = geodesic(current_pos, delivery['coords']).km
            total_distance += distance
            duree = int((distance / 50) * 60)  # Vitesse moyenne 50 km/h
            
            heure_actuelle = datetime.combine(datetime.today(), heure_actuelle.time())
            heure_actuelle = heure_actuelle + pd.Timedelta(minutes=duree + 15)  # +15 min livraison
            
            route_data.append({
                'N°': i,
                'Client': delivery['Client'],
                'Adresse': delivery['Adresse'],
                'Heure estimée': delivery['Heure_imposee'] if delivery['Heure_imposee'] else heure_actuelle.strftime("%H:%M"),
                'Distance (km)': f"{distance:.1f}",
                'Durée (min)': duree
            })
            
            current_pos = delivery['coords']
        
        # Retour au dépôt
        distance_retour = geodesic(current_pos, st.session_state.depot['coords']).km
        total_distance += distance_retour
        
        df = pd.DataFrame(route_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Statistiques
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        with col_stat1:
            st.metric("📏 Distance totale", f"{total_distance:.1f} km")
        with col_stat2:
            st.metric("⏱️ Durée estimée", f"{int((total_distance/50)*60)} min")
        with col_stat3:
            st.metric("📦 Livraisons", len(st.session_state.route_optimized))
        
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
            st.download_button("📥 Télécharger CSV", csv, "tournee.csv", "text/csv", use_container_width=True)
        
    else:
        # Affichage non optimisé
        df_simple = pd.DataFrame([{
            'Client': d['Client'],
            'Adresse': d['Adresse'],
            'Heure imposée': d['Heure_imposee'] if d['Heure_imposee'] else "—"
        } for d in st.session_state.livraisons])
        
        st.dataframe(df_simple, use_container_width=True, hide_index=True)
        st.warning("⚠️ Cliquez sur **OPTIMISER** pour calculer l'itinéraire optimal")

else:
    st.info("👆 Commencez par définir le dépôt, puis ajoutez des livraisons")

st.divider()
st.caption("💡 **Astuce** : Laissez l'heure vide pour laisser l'algorithme optimiser. Indiquez une heure uniquement si elle est imposée par le client.")
