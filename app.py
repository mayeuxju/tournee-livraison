import streamlit as st
import pandas as pd
import googlemaps
from datetime import datetime, timedelta
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go

# Configuration de la page
st.set_page_config(
    page_title="Optimisation Tournées - Suisse",
    page_icon="🚚",
    layout="wide"
)

# Initialisation de Google Maps
@st.cache_resource
def init_gmaps():
    try:
        api_key = st.secrets["google"]["api_key"]
        return googlemaps.Client(key=api_key)
    except Exception as e:
        st.error(f"❌ Erreur de connexion Google Maps : {str(e)}")
        return None

gmaps = init_gmaps()

# Initialisation de la session
if 'etape' not in st.session_state:
    st.session_state.etape = 1
if 'vehicule' not in st.session_state:
    st.session_state.vehicule = None
if 'depot' not in st.session_state:
    st.session_state.depot = None
if 'clients' not in st.session_state:
    st.session_state.clients = []
if 'tournee_optimisee' not in st.session_state:
    st.session_state.tournee_optimisee = None

# Fonction de géocodage intelligent
def geocoder_adresse(numero, rue, npa, ville):
    """
    Géocode une adresse suisse avec champs séparés
    Accepte des champs partiels
    """
    if not gmaps:
        return None, "❌ Google Maps non disponible"
    
    # Construction de l'adresse
    adresse_parts = []
    if numero and rue:
        adresse_parts.append(f"{numero} {rue}")
    elif rue:
        adresse_parts.append(rue)
    
    if npa:
        adresse_parts.append(str(npa))
    
    if ville:
        adresse_parts.append(ville)
    
    if not adresse_parts:
        return None, "❌ Aucune information d'adresse fournie"
    
    adresse_complete = ", ".join(adresse_parts) + ", Suisse"
    
    try:
        geocode_result = gmaps.geocode(adresse_complete)
        
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            adresse_formatee = geocode_result[0]['formatted_address']
            
            return {
                'lat': location['lat'],
                'lng': location['lng'],
                'adresse_formatee': adresse_formatee
            }, None
        else:
            return None, f"❌ Adresse introuvable : {adresse_complete}"
    
    except Exception as e:
        return None, f"❌ Erreur de géocodage : {str(e)}"

# Fonction de calcul de distance
def calculer_distance(origin, destination, mode_vehicule):
    """
    Calcule distance et temps entre 2 points
    mode_vehicule: 'truck' ou 'car'
    """
    if not gmaps:
        return None, None
    
    try:
        mode = "driving"  # Google Maps n'a pas de mode "truck"
        
        result = gmaps.distance_matrix(
            origins=[(origin['lat'], origin['lng'])],
            destinations=[(destination['lat'], destination['lng'])],
            mode=mode,
            departure_time=datetime.now()
        )
        
        if result['rows'][0]['elements'][0]['status'] == 'OK':
            distance_m = result['rows'][0]['elements'][0]['distance']['value']
            duree_s = result['rows'][0]['elements'][0]['duration']['value']
            
            # Ajustement pour camion (+20% de temps)
            if mode_vehicule == 'truck':
                duree_s = int(duree_s * 1.2)
            
            return distance_m / 1000, duree_s / 60  # km, minutes
        
        return None, None
    
    except Exception as e:
        st.error(f"Erreur calcul distance : {str(e)}")
        return None, None

# Titre principal
st.title("🚚 Optimisation de Tournées - Suisse")
st.markdown("---")

# ============================================================
# ÉTAPE 1 : CHOIX DU VÉHICULE
# ============================================================
if st.session_state.etape == 1:
    st.header("🚗 ÉTAPE 1 : Choix du véhicule")
    st.write("Sélectionnez le type de véhicule pour adapter les calculs de temps de trajet.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🚚 CAMION", use_container_width=True, type="primary"):
            st.session_state.vehicule = 'truck'
            st.session_state.etape = 2
            st.rerun()
        
        st.caption("Temps de trajet +20%")
    
    with col2:
        if st.button("🚗 VOITURE", use_container_width=True, type="primary"):
            st.session_state.vehicule = 'car'
            st.session_state.etape = 2
            st.rerun()
        
        st.caption("Temps de trajet standard")

# ============================================================
# ÉTAPE 2 : DÉFINIR LE DÉPÔT
# ============================================================
elif st.session_state.etape == 2:
    st.header("🏭 ÉTAPE 2 : Définir le dépôt")
    st.write(f"**Véhicule sélectionné :** {'🚚 Camion' if st.session_state.vehicule == 'truck' else '🚗 Voiture'}")
    
    st.markdown("### 📍 Adresse du dépôt")
    st.caption("Remplissez les champs disponibles (pas besoin de tous les remplir si l'info suffit)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        depot_numero = st.text_input("N° de rue", key="depot_numero")
        depot_rue = st.text_input("Nom de rue", key="depot_rue")
    
    with col2:
        depot_npa = st.text_input("NPA (Code postal)", key="depot_npa")
        depot_ville = st.text_input("Ville", key="depot_ville")
    
    col_btn1, col_btn2 = st.columns([1, 1])
    
    with col_btn1:
        if st.button("🔍 Valider le dépôt", type="primary", use_container_width=True):
            result, error = geocoder_adresse(
                depot_numero, 
                depot_rue, 
                depot_npa, 
                depot_ville
            )
            
            if result:
                st.session_state.depot = {
                    'numero': depot_numero,
                    'rue': depot_rue,
                    'npa': depot_npa,
                    'ville': depot_ville,
                    'lat': result['lat'],
                    'lng': result['lng'],
                    'adresse_formatee': result['adresse_formatee']
                }
                st.success(f"✅ Dépôt trouvé : {result['adresse_formatee']}")
                st.session_state.etape = 3
                st.rerun()
            else:
                st.error(error)
    
    with col_btn2:
        if st.button("← Retour", use_container_width=True):
            st.session_state.etape = 1
            st.rerun()

# ============================================================
# ÉTAPE 3 : AJOUTER LES CLIENTS
# ============================================================
elif st.session_state.etape == 3:
    st.header("👥 ÉTAPE 3 : Ajouter les clients")
    
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.info(f"**Véhicule :** {'🚚 Camion' if st.session_state.vehicule == 'truck' else '🚗 Voiture'}")
    with col_info2:
        st.info(f"**Dépôt :** {st.session_state.depot['adresse_formatee']}")
    
    st.markdown("---")
    
    # Liste des clients déjà ajoutés
    if st.session_state.clients:
        st.subheader(f"📋 Clients ajoutés ({len(st.session_state.clients)})")
        
        for idx, client in enumerate(st.session_state.clients):
            with st.expander(f"**{client['nom']}** - {client['adresse_formatee']}", expanded=False):
                col1, col2, col3 = st.columns([3, 2, 1])
                
                with col1:
                    st.write(f"📍 {client['adresse_formatee']}")
                    st.write(f"🕐 Fenêtre : **{client['heure_debut']} - {client['heure_fin']}**")
                
                with col2:
                    st.write(f"⏱️ Durée livraison : **{client['duree_livraison']} min**")
                
                with col3:
                    if st.button("🗑️", key=f"del_{idx}"):
                        st.session_state.clients.pop(idx)
                        st.rerun()
        
        st.markdown("---")
    
    # Formulaire d'ajout de client
    st.subheader("➕ Ajouter un nouveau client")
    
    # Conserver les valeurs en cas d'erreur
    if 'form_data' not in st.session_state:
        st.session_state.form_data = {
            'nom': '', 'numero': '', 'rue': '', 'npa': '', 'ville': '',
            'heure_debut': datetime.strptime("09:00", "%H:%M").time(),
            'heure_fin': datetime.strptime("17:00", "%H:%M").time(),
            'duree': 15
        }
    
    nom_client = st.text_input("👤 Nom du client", value=st.session_state.form_data['nom'])
    
    col1, col2 = st.columns(2)
    with col1:
        numero = st.text_input("N° de rue", value=st.session_state.form_data['numero'])
        rue = st.text_input("Nom de rue", value=st.session_state.form_data['rue'])
    
    with col2:
        npa = st.text_input("NPA", value=st.session_state.form_data['npa'])
        ville = st.text_input("Ville", value=st.session_state.form_data['ville'])
    
    col3, col4, col5 = st.columns(3)
    with col3:
        heure_debut = st.time_input("🕐 Début fenêtre", value=st.session_state.form_data['heure_debut'])
    with col4:
        heure_fin = st.time_input("🕐 Fin fenêtre", value=st.session_state.form_data['heure_fin'])
    with col5:
        duree_livraison = st.number_input("⏱️ Durée (min)", min_value=5, max_value=120, value=st.session_state.form_data['duree'])
    
    col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 1])
    
    with col_btn1:
        if st.button("➕ Ajouter ce client", type="primary", use_container_width=True):
            # Sauvegarder les données du formulaire
            st.session_state.form_data = {
                'nom': nom_client,
                'numero': numero,
                'rue': rue,
                'npa': npa,
                'ville': ville,
                'heure_debut': heure_debut,
                'heure_fin': heure_fin,
                'duree': duree_livraison
            }
            
            if not nom_client:
                st.error("❌ Le nom du client est obligatoire")
            else:
                result, error = geocoder_adresse(numero, rue, npa, ville)
                
                if result:
                    client = {
                        'nom': nom_client,
                        'numero': numero,
                        'rue': rue,
                        'npa': npa,
                        'ville': ville,
                        'lat': result['lat'],
                        'lng': result['lng'],
                        'adresse_formatee': result['adresse_formatee'],
                        'heure_debut': heure_debut.strftime("%H:%M"),
                        'heure_fin': heure_fin.strftime("%H:%M"),
                        'duree_livraison': duree_livraison
                    }
                    
                    st.session_state.clients.append(client)
                    
                    # Réinitialiser le formulaire UNIQUEMENT en cas de succès
                    st.session_state.form_data = {
                        'nom': '', 'numero': '', 'rue': '', 'npa': '', 'ville': '',
                        'heure_debut': datetime.strptime("09:00", "%H:%M").time(),
                        'heure_fin': datetime.strptime("17:00", "%H:%M").time(),
                        'duree': 15
                    }
                    
                    st.success(f"✅ {nom_client} ajouté !")
                    st.rerun()
                else:
                    st.error(error)
                    st.warning("⚠️ Les informations saisies sont conservées. Corrigez l'adresse et réessayez.")
    
    with col_btn2:
        if st.session_state.clients:
            if st.button("🚀 Optimiser la tournée", type="primary", use_container_width=True):
                st.session_state.etape = 4
                st.rerun()
    
    with col_btn3:
        if st.button("← Retour", use_container_width=True):
            st.session_state.etape = 2
            st.rerun()

# ============================================================
# ÉTAPE 4 : OPTIMISATION DE LA TOURNÉE
# ============================================================
elif st.session_state.etape == 4:
    st.header("🚀 ÉTAPE 4 : Tournée optimisée")
    
    col_info1, col_info2, col_info3 = st.columns(3)
    with col_info1:
        st.info(f"**Véhicule :** {'🚚 Camion' if st.session_state.vehicule == 'truck' else '🚗 Voiture'}")
    with col_info2:
        st.info(f"**Dépôt :** {st.session_state.depot['ville']}")
    with col_info3:
        st.info(f"**Clients :** {len(st.session_state.clients)}")
    
    st.markdown("---")
    
    # Calcul de la tournée optimisée
    with st.spinner("🔄 Optimisation en cours..."):
        # Algorithme du plus proche voisin
        points_restants = st.session_state.clients.copy()
        tournee = []
        position_actuelle = st.session_state.depot
        
        while points_restants:
            distances = []
            for client in points_restants:
                dist, temps = calculer_distance(position_actuelle, client, st.session_state.vehicule)
                if dist is not None:
                    distances.append((client, dist, temps))
            
            if not distances:
                break
            
            # Trier par distance
            distances.sort(key=lambda x: x[1])
            prochain_client, distance, temps = distances[0]
            
            tournee.append({
                'client': prochain_client,
                'distance_km': round(distance, 1),
                'temps_trajet_min': round(temps, 0)
            })
            
            points_restants.remove(prochain_client)
            position_actuelle = prochain_client
        
        # Retour au dépôt
        dist_retour, temps_retour = calculer_distance(position_actuelle, st.session_state.depot, st.session_state.vehicule)
        
        st.session_state.tournee_optimisee = tournee
    
    # Affichage de la tournée
    st.subheader("📋 Ordre de livraison optimisé")
    
    distance_totale = 0
    temps_total = 0
    
    # Tableau de la tournée
    st.markdown("### 🏭 Départ du dépôt")
    st.write(f"**{st.session_state.depot['adresse_formatee']}**")
    
    for idx, etape in enumerate(tournee, 1):
        client = etape['client']
        distance = etape['distance_km']
        temps = etape['temps_trajet_min']
        
        distance_totale += distance
        temps_total += temps + client['duree_livraison']
        
        st.markdown(f"### ↓ {distance} km · {int(temps)} min")
        
        with st.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"### 📍 **{idx}. {client['nom']}**")
                st.write(f"**{client['adresse_formatee']}**")
                st.write(f"🕐 Fenêtre : {client['heure_debut']} - {client['heure_fin']} · ⏱️ Livraison : {client['duree_livraison']} min")
            with col2:
                st.metric("Distance", f"{distance} km")
                st.metric("Trajet", f"{int(temps)} min")
    
    if dist_retour:
        distance_totale += dist_retour
        temps_total += temps_retour
        
        st.markdown(f"### ↓ {round(dist_retour, 1)} km · {int(temps_retour)} min")
    
    st.markdown("### 🏭 Retour au dépôt")
    st.write(f"**{st.session_state.depot['adresse_formatee']}**")
    
    st.markdown("---")
    
    # Statistiques
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("🚗 Distance totale", f"{round(distance_totale, 1)} km")
    with col2:
        st.metric("⏱️ Temps total", f"{int(temps_total)} min ({temps_total/60:.1f}h)")
    with col3:
        st.metric("📦 Livraisons", len(tournee))
    
    st.markdown("---")
    
    # Carte
    st.subheader("🗺️ Carte de la tournée")
    
    m = folium.Map(location=[st.session_state.depot['lat'], st.session_state.depot['lng']], zoom_start=10)
    
    # Marqueur dépôt
    folium.Marker(
        location=[st.session_state.depot['lat'], st.session_state.depot['lng']],
        popup="🏭 DÉPÔT",
        tooltip="Départ",
        icon=folium.Icon(color='green', icon='home', prefix='glyphicon')
    ).add_to(m)
    
    # Marqueurs clients
    for idx, etape in enumerate(tournee, 1):
        client = etape['client']
        folium.Marker(
            location=[client['lat'], client['lng']],
            popup=f"<b>{idx}. {client['nom']}</b><br>{client['adresse_formatee']}",
            tooltip=f"{idx}. {client['nom']}",
            icon=folium.Icon(color='red', icon='info-sign', prefix='glyphicon')
        ).add_to(m)
    
    # Tracer la route
    coords = [[st.session_state.depot['lat'], st.session_state.depot['lng']]]
    for etape in tournee:
        coords.append([etape['client']['lat'], etape['client']['lng']])
    coords.append([st.session_state.depot['lat'], st.session_state.depot['lng']])
    
    folium.PolyLine(coords, color='blue', weight=3, opacity=0.7).add_to(m)
    
    st_folium(m, width=700, height=500)
    
    st.markdown("---")
    
    # Boutons d'action
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Export CSV
        df_export = pd.DataFrame([{
            'Ordre': idx,
            'Client': etape['client']['nom'],
            'Adresse': etape['client']['adresse_formatee'],
            'Distance (km)': etape['distance_km'],
            'Temps trajet (min)': int(etape['temps_trajet_min']),
            'Durée livraison (min)': etape['client']['duree_livraison'],
            'Fenêtre horaire': f"{etape['client']['heure_debut']} - {etape['client']['heure_fin']}"
        } for idx, etape in enumerate(tournee, 1)])
        
        csv = df_export.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Télécharger CSV",
            data=csv,
            file_name=f"tournee_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col2:
        # Lien Google Maps
        waypoints = [f"{st.session_state.depot['lat']},{st.session_state.depot['lng']}"]
        for etape in tournee:
            waypoints.append(f"{etape['client']['lat']},{etape['client']['lng']}")
        waypoints.append(f"{st.session_state.depot['lat']},{st.session_state.depot['lng']}")
        
        gmaps_url = f"https://www.google.com/maps/dir/{'/'.join(waypoints)}"
        st.link_button("🗺️ Ouvrir dans Google Maps", gmaps_url, use_container_width=True)
    
    with col3:
        if st.button("🔄 Nouvelle tournée", use_container_width=True):
            st.session_state.etape = 1
            st.session_state.clients = []
            st.session_state.depot = None
            st.session_state.vehicule = None
            st.session_state.tournee_optimisee = None
            st.rerun()
    
    col_back1, col_back2 = st.columns([1, 5])
    with col_back1:
        if st.button("← Modifier clients", use_container_width=True):
            st.session_state.etape = 3
            st.rerun()

st.markdown("---")
st.caption("💡 Application développée pour l'optimisation de tournées en Suisse · Véhicules : Camion (+20% temps) / Voiture")
