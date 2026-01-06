import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import datetime

# Configuration page
st.set_page_config(page_title="Tournées Livraison", page_icon="🚚", layout="wide")

# Titre
st.title("🚚 Optimiseur de Tournées")
st.markdown("**Application mobile pour chauffeurs poids-lourds**")

# Initialisation
if 'deliveries' not in st.session_state:
    st.session_state.deliveries = []

geolocator = Nominatim(user_agent="delivery_optimizer_v1")

# ===== SECTION 1 : AJOUT DE LIVRAISONS =====
st.header("📍 Ajouter une livraison")

col1, col2 = st.columns(2)

with col1:
    client_name = st.text_input("Nom du client", placeholder="Ex: Client A")
    address = st.text_input("Adresse complète", placeholder="Ex: 5 Rue de Rivoli, 75001 Paris")

with col2:
    time_start = st.time_input("Heure début fenêtre", value=datetime.strptime("09:00", "%H:%M").time())
    time_end = st.time_input("Heure fin fenêtre", value=datetime.strptime("11:00", "%H:%M").time())

if st.button("➕ Ajouter cette livraison", type="primary"):
    if not client_name or not address:
        st.error("⚠️ Remplissez le nom et l'adresse")
    else:
        with st.spinner(f"Géocodage de {address}..."):
            try:
                location = geolocator.geocode(address, timeout=10)
                if location:
                    st.session_state.deliveries.append({
                        'nom': client_name,
                        'adresse': address,
                        'lat': location.latitude,
                        'lon': location.longitude,
                        'debut': time_start.strftime("%H:%M"),
                        'fin': time_end.strftime("%H:%M")
                    })
                    st.success(f"✅ {client_name} ajouté !")
                else:
                    st.error("❌ Adresse introuvable")
            except Exception as e:
                st.error(f"❌ Erreur : {e}")

# ===== SECTION 2 : LISTE DES LIVRAISONS =====
st.divider()
st.header(f"📦 Livraisons enregistrées ({len(st.session_state.deliveries)})")

if st.session_state.deliveries:
    df = pd.DataFrame(st.session_state.deliveries)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🗑️ Effacer tout", type="secondary"):
            st.session_state.deliveries = []
            st.rerun()
    
    # ===== SECTION 3 : OPTIMISATION =====
    with col_btn2:
        if st.button("🚀 OPTIMISER LA TOURNÉE", type="primary"):
            if len(st.session_state.deliveries) < 2:
                st.error("❌ Il faut au moins 2 livraisons")
            else:
                st.divider()
                st.header("✅ TOURNÉE OPTIMISÉE")
                
                # Tri par heure de début (optimisation simple)
                sorted_deliveries = sorted(st.session_state.deliveries, key=lambda x: x['debut'])
                
                # Affichage de la tournée
                total_distance = 0
                for i, delivery in enumerate(sorted_deliveries, 1):
                    if i == 1:
                        st.markdown(f"### {i}. 🏁 {delivery['nom']}")
                        st.caption(f"📍 {delivery['adresse']}")
                        st.caption(f"🕐 Départ : {delivery['debut']}")
                    else:
                        # Calculer distance depuis le point précédent
                        prev = sorted_deliveries[i-2]
                        distance = geodesic(
                            (prev['lat'], prev['lon']),
                            (delivery['lat'], delivery['lon'])
                        ).km
                        total_distance += distance
                        
                        st.markdown(f"### {i}. 📦 {delivery['nom']}")
                        st.caption(f"📍 {delivery['adresse']}")
                        st.caption(f"🕐 Fenêtre : {delivery['debut']} - {delivery['fin']}")
                        st.caption(f"🛣️ Distance depuis point précédent : **{distance:.2f} km**")
                    
                    st.divider()
                
                # Métriques
                st.metric("📏 Distance totale estimée", f"{total_distance:.2f} km")
                st.metric("⏱️ Temps de trajet estimé", f"{int(total_distance * 2)} minutes")
                
                # ===== SECTION 4 : EXPORT GOOGLE MAPS =====
                st.header("🗺️ Navigation")
                
                # Créer l'URL Google Maps
                waypoints = "/".join([f"{d['lat']},{d['lon']}" for d in sorted_deliveries])
                google_maps_url = f"https://www.google.com/maps/dir/{waypoints}"
                
                st.markdown(f"### [🚗 OUVRIR DANS GOOGLE MAPS]({google_maps_url})")
                st.caption("👆 Cliquez pour lancer la navigation GPS")
                
                # Afficher l'URL pour copie manuelle
                with st.expander("📋 Copier le lien manuellement"):
                    st.code(google_maps_url, language=None)
                
                # Détail de chaque étape
                with st.expander("📍 Voir les coordonnées GPS"):
                    for i, d in enumerate(sorted_deliveries, 1):
                        st.text(f"{i}. {d['nom']}: {d['lat']}, {d['lon']}")

else:
    st.info("👆 Ajoutez votre première livraison ci-dessus")

# Footer
st.divider()
st.caption("💡 **Astuce** : Ajoutez d'abord votre dépôt (point de départ), puis vos clients")
st.caption("🔄 Rafraîchissez la page pour recommencer")
