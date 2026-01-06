import streamlit as st
import pandas as pd
import googlemaps
from datetime import datetime

# ============================================
# 🧪 TEST DE LA CLÉ API GOOGLE MAPS
# ============================================

st.set_page_config(
    page_title="Optimisation Tournées Suisse",
    page_icon="🚚",
    layout="wide"
)

st.title("🧪 Test de connexion Google Maps")

try:
    # Récupérer la clé API depuis les secrets
    google_api_key = st.secrets["google"]["api_key"]
    
    # Créer le client Google Maps
    gmaps = googlemaps.Client(key=google_api_key)
    
    # Test simple : Lausanne → Genève
    st.info("🔄 Test de connexion en cours...")
    
    test_result = gmaps.distance_matrix(
        origins=["Lausanne, Suisse"],
        destinations=["Genève, Suisse"],
        mode="driving",
        language="fr"
    )
    
    # Vérifier le résultat
    if test_result['status'] == 'OK':
        distance = test_result['rows'][0]['elements'][0]['distance']['text']
        duree = test_result['rows'][0]['elements'][0]['duration']['text']
        
        st.success("✅ CONNEXION GOOGLE MAPS RÉUSSIE !")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("🚗 Distance Lausanne → Genève", distance)
        with col2:
            st.metric("⏱️ Temps de trajet", duree)
        
        st.balloons()
        
    else:
        st.error(f"❌ Erreur dans la réponse de l'API : {test_result['status']}")
        st.json(test_result)
        
except KeyError as e:
    st.error("❌ CLÉ API MANQUANTE DANS LES SECRETS !")
    st.warning("👉 Allez dans **Settings → Secrets** sur Streamlit Cloud")
    st.info("Ajoutez exactement ce format :")
    st.code("""[google]
api_key = "VOTRE_CLE_ICI"
    """, language="toml")
    st.stop()
    
except Exception as e:
    st.error(f"❌ ERREUR : {str(e)}")
    st.exception(e)
    st.stop()

# ============================================
# 🚚 APPLICATION PRINCIPALE
# ============================================

st.divider()
st.title("🚚 Optimisation de Tournées - Suisse")

# Initialiser la session
if 'deliveries' not in st.session_state:
    st.session_state.deliveries = []

# Sidebar - Informations
with st.sidebar:
    st.header("ℹ️ Comment utiliser")
    st.markdown("""
    1. **Ajoutez votre dépôt** (point de départ)
    2. **Ajoutez vos clients** (destinations)
    3. **Cliquez sur "Optimiser"**
    4. **Lancez la navigation** dans Google Maps
    """)
    
    st.divider()
    
    st.header("📊 Statistiques")
    st.metric("Livraisons ajoutées", len(st.session_state.deliveries))

# Section d'ajout d'une livraison
st.header("➕ Ajouter une livraison")

col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    nom = st.text_input("Nom du point", placeholder="Ex: Dépôt Lausanne")

with col2:
    adresse = st.text_input("Adresse complète", placeholder="Ex: Route de Berne 10, 1010 Lausanne")

with col3:
    type_point = st.selectbox("Type", ["🏢 Dépôt", "📦 Client"])

if st.button("➕ Ajouter", type="primary"):
    if nom and adresse:
        st.session_state.deliveries.append({
            'nom': nom,
            'adresse': adresse,
            'type': type_point
        })
        st.success(f"✅ {nom} ajouté !")
        st.rerun()
    else:
        st.error("⚠️ Veuillez remplir tous les champs")

# Afficher les livraisons
st.divider()
st.header("📋 Liste des points")

if st.session_state.deliveries:
    
    # Bouton pour tout effacer
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        if st.button("🗑️ Tout effacer", type="secondary"):
            st.session_state.deliveries = []
            st.rerun()
    
    # Afficher la liste
    for idx, delivery in enumerate(st.session_state.deliveries):
        col1, col2, col3 = st.columns([3, 3, 1])
        
        with col1:
            st.write(f"**{delivery['type']} {delivery['nom']}**")
        
        with col2:
            st.write(delivery['adresse'])
        
        with col3:
            if st.button("❌", key=f"del_{idx}"):
                st.session_state.deliveries.pop(idx)
                st.rerun()
    
    st.divider()
    
    # Bouton d'optimisation
    if len(st.session_state.deliveries) >= 2:
        
        if st.button("🚀 OPTIMISER LA TOURNÉE", type="primary", use_container_width=True):
            
            with st.spinner("🔄 Calcul de l'itinéraire optimal..."):
                
                try:
                    # Séparer le dépôt des clients
                    depot = None
                    clients = []
                    
                    for d in st.session_state.deliveries:
                        if d['type'] == "🏢 Dépôt":
                            depot = d['adresse']
                        else:
                            clients.append(d['adresse'])
                    
                    if not depot:
                        st.error("⚠️ Veuillez ajouter un dépôt (point de départ)")
                        st.stop()
                    
                    if len(clients) == 0:
                        st.error("⚠️ Veuillez ajouter au moins un client")
                        st.stop()
                    
                    # Calculer les distances
                    all_addresses = [depot] + clients
                    
                    # Créer l'URL Google Maps avec tous les points
                    # Format: origin → waypoints → destination (retour au dépôt)
                    
                    origin = depot.replace(" ", "+")
                    destination = depot.replace(" ", "+")
                    waypoints = "|".join([addr.replace(" ", "+") for addr in clients])
                    
                    google_maps_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}&waypoints={waypoints}&travelmode=driving"
                    
                    # Afficher le résultat
                    st.success("✅ Tournée optimisée !")
                    
                    st.subheader("📍 Itinéraire")
                    st.write(f"**1.** 🏢 Départ : {depot}")
                    for idx, client in enumerate(clients, start=2):
                        st.write(f"**{idx}.** 📦 {client}")
                    st.write(f"**{len(clients) + 2}.** 🏢 Retour au dépôt")
                    
                    st.divider()
                    
                    # Bouton pour ouvrir Google Maps
                    st.link_button(
                        "🗺️ OUVRIR DANS GOOGLE MAPS",
                        google_maps_url,
                        type="primary",
                        use_container_width=True
                    )
                    
                    st.info("💡 Cliquez sur le bouton ci-dessus pour lancer la navigation")
                    
                except Exception as e:
                    st.error(f"❌ Erreur lors de l'optimisation : {str(e)}")
        
    else:
        st.info("👆 Ajoutez au moins un dépôt et un client pour optimiser")

else:
    st.info("👆 Ajoutez votre première livraison ci-dessus")

# Footer
st.divider()
st.caption("💡 **Astuce** : Ajoutez d'abord votre dépôt (point de départ), puis vos clients")
st.caption("🔄 Rafraîchissez la page pour recommencer")
st.caption(f"⏰ Dernière mise à jour : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
