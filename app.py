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
    
    # Construction de l'adresse - PLUSIEURS TENTATIVES
    tentatives = []
    
    # Tentative 1 : Adresse complète
    if numero and rue and npa and ville:
        tentatives.append(f"{rue} {numero}, {npa} {ville}, Suisse")
    
    # Tentative 2 : Sans numéro
    if rue and npa and ville:
        tentatives.append(f"{rue}, {npa} {ville}, Suisse")
    
    # Tentative 3 : Ville + NPA seulement
    if npa and ville:
        tentatives.append(f"{npa} {ville}, Suisse")
    
    # Tentative 4 : Ville seulement
    if ville:
        tentatives.append(f"{ville}, Suisse")
    
    if not tentatives:
        return None, "❌ Aucune information d'adresse fournie"
    
    # Essayer chaque tentative
    for idx, adresse in enumerate(tentatives):
        try:
            geocode_result = gmaps.geocode(
                adresse,
                components={'country': 'CH'}  # Forcer la Suisse
            )
            
            if geocode_result:
                location = geocode_result[0]['geometry']['location']
                adresse_formatee = geocode_result[0]['formatted_address']
                
                # Vérifier que c'est bien en Suisse
                if 'Switzerland' in adresse_formatee or 'Suisse' in adresse_formatee or 'Schweiz' in adresse_formatee:
                    return {
                        'lat': location['lat'],
                        'lng': location['lng'],
                        'adresse_formatee': adresse_formatee
                    }, None
        
        except Exception as e:
            # Continuer avec la tentative suivante
            if idx == len(tentatives) - 1:  # Dernière tentative
                error_msg = str(e)
                
                # Messages d'erreur spécifiques
                if 'OVER_QUERY_LIMIT' in error_msg:
                    return None, "❌ Quota API Google Maps dépassé. Réessayez dans quelques minutes."
                elif 'REQUEST_DENIED' in error_msg:
                    return None, "❌ API Google Maps : Requête refusée. Vérifiez la configuration."
                elif 'INVALID_REQUEST' in error_msg:
                    return None, f"❌ Adresse invalide : {adresse}"
                else:
                    return None, f"❌ Erreur : {error_msg[:100]}"
            continue
    
    return None, f"❌ Adresse introuvable. Tentatives effectuées : {len(tentatives)}"

# Fonction pour calculer la matrice des distances
def calculer_matrice_distances(points):
    """Calcule les distances entre tous les points"""
    if not gmaps or len(points) < 2:
        return None
    
    coords = [f"{p['lat']},{p['lng']}" for p in points]
    
    try:
        matrix = gmaps.distance_matrix(
            origins=coords,
            destinations=coords,
            mode="driving",
            units="metric"
        )
        return matrix
    except Exception as e:
        st.error(f"Erreur calcul distances : {str(e)}")
        return None

# Fonction d'optimisation simple
def optimiser_tournee(depot, clients, vehicule):
    """Optimise l'ordre des clients (algorithme du plus proche voisin)"""
    if not clients:
        return []
    
    tournee = []
    clients_restants = clients.copy()
    position_actuelle = depot
    heure_actuelle = datetime.strptime("08:00", "%H:%M")
    
    # Coefficient véhicule
    coef_vehicule = 1.2 if vehicule == "🚚 Camion" else 1.0
    
    while clients_restants:
        # Trouver le client le plus proche
        distances = []
        for client in clients_restants:
            if gmaps:
                try:
                    result = gmaps.distance_matrix(
                        origins=[f"{position_actuelle['lat']},{position_actuelle['lng']}"],
                        destinations=[f"{client['lat']},{client['lng']}"],
                        mode="driving"
                    )
                    
                    if result['rows'][0]['elements'][0]['status'] == 'OK':
                        distance_m = result['rows'][0]['elements'][0]['distance']['value']
                        duree_s = result['rows'][0]['elements'][0]['duration']['value']
                        distances.append({
                            'client': client,
                            'distance': distance_m,
                            'duree': duree_s
                        })
                except:
                    pass
        
        if not distances:
            # Fallback : distance à vol d'oiseau
            for client in clients_restants:
                dist = ((client['lat'] - position_actuelle['lat'])**2 + 
                       (client['lng'] - position_actuelle['lng'])**2)**0.5 * 111000
                distances.append({
                    'client': client,
                    'distance': dist,
                    'duree': dist / 13.89  # ~50 km/h
                })
        
        # Sélectionner le plus proche
        plus_proche = min(distances, key=lambda x: x['distance'])
        
        # Calculer les horaires
        duree_trajet = int(plus_proche['duree'] * coef_vehicule)
        heure_arrivee = heure_actuelle + timedelta(seconds=duree_trajet)
        
        # Vérifier fenêtre horaire
        if plus_proche['client'].get('heure_debut'):
            heure_debut = datetime.strptime(plus_proche['client']['heure_debut'], "%H:%M")
            if heure_arrivee < heure_debut:
                temps_attente = (heure_debut - heure_arrivee).seconds // 60
                heure_arrivee = heure_debut
            else:
                temps_attente = 0
        else:
            temps_attente = 0
        
        # Ajouter durée de livraison
        duree_livraison = plus_proche['client'].get('duree_livraison', 15)
        heure_depart = heure_arrivee + timedelta(minutes=duree_livraison)
        
        tournee.append({
            'ordre': len(tournee) + 1,
            'client': plus_proche['client'],
            'distance_km': plus_proche['distance'] / 1000,
            'duree_trajet_min': duree_trajet // 60,
            'heure_arrivee': heure_arrivee.strftime("%H:%M"),
            'temps_attente_min': temps_attente,
            'heure_depart': heure_depart.strftime("%H:%M")
        })
        
        # Mise à jour pour prochaine itération
        clients_restants.remove(plus_proche['client'])
        position_actuelle = plus_proche['client']
        heure_actuelle = heure_depart
    
    # Retour au dépôt
    if gmaps:
        try:
            result = gmaps.distance_matrix(
                origins=[f"{position_actuelle['lat']},{position_actuelle['lng']}"],
                destinations=[f"{depot['lat']},{depot['lng']}"],
                mode="driving"
            )
            if result['rows'][0]['elements'][0]['status'] == 'OK':
                distance_retour = result['rows'][0]['elements'][0]['distance']['value'] / 1000
                duree_retour = int(result['rows'][0]['elements'][0]['duration']['value'] * coef_vehicule) // 60
            else:
                distance_retour = 0
                duree_retour = 0
        except:
            distance_retour = 0
            duree_retour = 0
    else:
        distance_retour = 0
        duree_retour = 0
    
    heure_retour = heure_actuelle + timedelta(minutes=duree_retour)
    
    tournee.append({
        'ordre': len(tournee) + 1,
        'client': {'nom': 'Retour au dépôt', 'adresse_formatee': depot['adresse_formatee']},
        'distance_km': distance_retour,
        'duree_trajet_min': duree_retour,
        'heure_arrivee': heure_retour.strftime("%H:%M"),
        'temps_attente_min': 0,
        'heure_depart': heure_retour.strftime("%H:%M")
    })
    
    return tournee

# ========================================
# INTERFACE PRINCIPALE
# ========================================

st.title("🚚 Optimisation de Tournées - Suisse")

# Mode debug (sidebar)
with st.sidebar:
    st.markdown("---")
    debug_mode = st.checkbox("🔧 Mode Debug", value=False)
    
    if debug_mode:
        st.write("**État de l'application :**")
        st.write(f"- Étape : {st.session_state.etape}")
        st.write(f"- Véhicule : {st.session_state.vehicule}")
        st.write(f"- Dépôt : {'✅' if st.session_state.depot else '❌'}")
        st.write(f"- Clients : {len(st.session_state.clients)}")
        
        if st.button("🔄 Reset complet"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

st.markdown("---")

# ========================================
# ÉTAPE 1 : CHOIX DU VÉHICULE
# ========================================

if st.session_state.etape == 1:
    st.header("🚗 ÉTAPE 1 : Choix du véhicule")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🚚 Camion\n(+20% temps)", use_container_width=True, type="primary"):
            st.session_state.vehicule = "🚚 Camion"
            st.session_state.etape = 2
            st.rerun()
    
    with col2:
        if st.button("🚗 Voiture\n(Temps standard)", use_container_width=True):
            st.session_state.vehicule = "🚗 Voiture"
            st.session_state.etape = 2
            st.rerun()
    
    st.info("💡 Le camion ajoute 20% au temps de trajet (vitesse réduite, manœuvres)")

# ========================================
# ÉTAPE 2 : DÉFINIR LE DÉPÔT
# ========================================

elif st.session_state.etape == 2:
    st.header("🏭 ÉTAPE 2 : Définir le dépôt")
    st.caption(f"Véhicule sélectionné : **{st.session_state.vehicule}**")
    
    st.subheader("📍 Adresse du dépôt")
    st.caption("Remplissez au moins la ville ou le NPA. Les autres champs sont optionnels.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        numero_depot = st.text_input("N° rue", key="numero_depot", placeholder="Ex: 10")
        npa_depot = st.text_input("NPA *", key="npa_depot", placeholder="Ex: 1003")
    
    with col2:
        rue_depot = st.text_input("Nom de rue", key="rue_depot", placeholder="Ex: Avenue de la Gare")
        ville_depot = st.text_input("Ville *", key="ville_depot", placeholder="Ex: Lausanne")
    
    col_btn1, col_btn2 = st.columns([3, 1])
    
    with col_btn1:
        if st.button("✅ Valider le dépôt", type="primary", use_container_width=True):
            if not ville_depot and not npa_depot:
                st.error("❌ Veuillez renseigner au moins la ville ou le NPA")
            else:
                with st.spinner("🔍 Recherche de l'adresse..."):
                    resultat, erreur = geocoder_adresse(numero_depot, rue_depot, npa_depot, ville_depot)
                    
                    if resultat:
                        st.session_state.depot = resultat
                        st.session_state.etape = 3
                        st.success(f"✅ Dépôt enregistré : {resultat['adresse_formatee']}")
                        st.rerun()
                    else:
                        st.error(erreur)
                        st.info("💡 Vérifiez l'orthographe ou simplifiez (ex: juste le NPA + ville)")
    
    with col_btn2:
        if st.button("← Retour", use_container_width=True):
            st.session_state.etape = 1
            st.rerun()

# ========================================
# ÉTAPE 3 : AJOUTER DES CLIENTS
# ========================================

elif st.session_state.etape == 3:
    st.header("👥 ÉTAPE 3 : Ajouter des clients")
    st.caption(f"Véhicule : **{st.session_state.vehicule}** · Dépôt : **{st.session_state.depot['adresse_formatee']}**")
    
    # Affichage de la liste des clients
    if st.session_state.clients:
        st.subheader(f"📋 Clients ajoutés ({len(st.session_state.clients)})")
        
        for idx, client in enumerate(st.session_state.clients):
            col1, col2, col3 = st.columns([3, 2, 1])
            
            with col1:
                st.write(f"**{client['nom']}**")
                st.caption(client['adresse_formatee'])
            
            with col2:
                fenetre = ""
                if client.get('heure_debut') and client.get('heure_fin'):
                    fenetre = f"🕐 {client['heure_debut']} - {client['heure_fin']}"
                st.caption(fenetre)
            
            with col3:
                if st.button("🗑️", key=f"del_{idx}", use_container_width=True):
                    st.session_state.clients.pop(idx)
                    st.rerun()
        
        st.markdown("---")
    
    # Formulaire d'ajout
    st.subheader("➕ Ajouter un nouveau client")
    
    nom_client = st.text_input("👤 Nom du client *", placeholder="Ex: Entreprise ABC")
    
    col1, col2 = st.columns(2)
    
    with col1:
        numero_client = st.text_input("N° rue", key="numero_client", placeholder="Ex: 25")
        npa_client = st.text_input("NPA *", key="npa_client", placeholder="Ex: 1003")
    
    with col2:
        rue_client = st.text_input("Nom de rue", key="rue_client", placeholder="Ex: Rue du Commerce")
        ville_client = st.text_input("Ville *", key="ville_client", placeholder="Ex: Lausanne")
    
    st.subheader("🕐 Horaires (optionnel)")
    
    col3, col4, col5 = st.columns(3)
    
    with col3:
        heure_debut = st.time_input("Heure début", value=None, step=900)
    
    with col4:
        heure_fin = st.time_input("Heure fin", value=None, step=900)
    
    with col5:
        duree_livraison = st.number_input("Durée livraison (min)", min_value=5, max_value=120, value=15)
    
    col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 1])
    
    with col_btn1:
        if st.button("✅ Ajouter ce client", type="primary", use_container_width=True):
            if not nom_client:
                st.error("❌ Le nom du client est obligatoire")
            elif not ville_client and not npa_client:
                st.error("❌ Veuillez renseigner au moins la ville ou le NPA")
            else:
                with st.spinner("🔍 Recherche de l'adresse..."):
                    resultat, erreur = geocoder_adresse(numero_client, rue_client, npa_client, ville_client)
                    
                    if resultat:
                        nouveau_client = {
                            'nom': nom_client,
                            'lat': resultat['lat'],
                            'lng': resultat['lng'],
                            'adresse_formatee': resultat['adresse_formatee'],
                            'duree_livraison': duree_livraison
                        }
                        
                        if heure_debut and heure_fin:
                            nouveau_client['heure_debut'] = heure_debut.strftime("%H:%M")
                            nouveau_client['heure_fin'] = heure_fin.strftime("%H:%M")
                        
                        st.session_state.clients.append(nouveau_client)
                        st.success(f"✅ Client ajouté : {resultat['adresse_formatee']}")
                        st.rerun()
                    else:
                        st.error(erreur)
                        st.info("💡 Les informations restent dans les champs. Corrigez et réessayez.")
    
    with col_btn2:
        if st.button("🚀 Optimiser la tournée", disabled=len(st.session_state.clients) == 0, use_container_width=True):
            st.session_state.etape = 4
            st.rerun()
    
    with col_btn3:
        if st.button("← Retour", use_container_width=True):
            st.session_state.etape = 2
            st.rerun()

# ========================================
# ÉTAPE 4 : TOURNÉE OPTIMISÉE
# ========================================

elif st.session_state.etape == 4:
    st.header("🎯 ÉTAPE 4 : Tournée optimisée")
    
    # Optimisation
    if st.session_state.tournee_optimisee is None:
        with st.spinner("⏳ Optimisation en cours..."):
            st.session_state.tournee_optimisee = optimiser_tournee(
                st.session_state.depot,
                st.session_state.clients,
                st.session_state.vehicule
            )
    
    tournee = st.session_state.tournee_optimisee
    
    # Résumé
    distance_totale = sum(e['distance_km'] for e in tournee)
    duree_totale = sum(e['duree_trajet_min'] for e in tournee[:-1])  # Sans retour
    nb_clients = len(tournee) - 1
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📍 Clients", nb_clients)
    col2.metric("🚗 Distance totale", f"{distance_totale:.1f} km")
    col3.metric("⏱️ Temps de trajet", f"{duree_totale} min")
    col4.metric("🕐 Fin estimée", tournee[-1]['heure_arrivee'])
    
    st.markdown("---")
    
    # Tableau de la tournée
    st.subheader("📋 Feuille de route")
    
    for etape in tournee:
        with st.container():
            col1, col2, col3, col4 = st.columns([1, 3, 2, 2])
            
            with col1:
                st.write(f"**#{etape['ordre']}**")
            
            with col2:
                st.write(f"**{etape['client']['nom']}**")
                st.caption(etape['client'].get('adresse_formatee', ''))
            
            with col3:
                st.write(f"🚗 {etape['distance_km']:.1f} km · ⏱️ {etape['duree_trajet_min']} min")
            
            with col4:
                st.write(f"🕐 Arrivée : **{etape['heure_arrivee']}**")
                if etape.get('temps_attente_min', 0) > 0:
                    st.caption(f"⏸️ Attente : {etape['temps_attente_min']} min")
                if etape.get('heure_depart'):
                    st.caption(f"🚀 Départ : {etape['heure_depart']}")
        
        st.markdown("---")
    
    # Carte interactive
    st.subheader("🗺️ Carte de la tournée")
    
    # Créer la carte
    carte = folium.Map(
        location=[st.session_state.depot['lat'], st.session_state.depot['lng']],
        zoom_start=12
    )
    
    # Marqueur dépôt
    folium.Marker(
        [st.session_state.depot['lat'], st.session_state.depot['lng']],
        popup="🏭 DÉPÔT",
        icon=folium.Icon(color='red', icon='home')
    ).add_to(carte)
    
    # Marqueurs clients
    for idx, etape in enumerate(tournee[:-1]):  # Sans le retour
        client = etape['client']
        folium.Marker(
            [client['lat'], client['lng']],
            popup=f"#{etape['ordre']} - {client['nom']}<br>{etape['heure_arrivee']}",
            icon=folium.Icon(color='blue', icon='info-sign', prefix='glyphicon')
        ).add_to(carte)
        
        # Numéro sur la carte
        folium.Marker(
            [client['lat'], client['lng']],
            icon=folium.DivIcon(html=f'<div style="font-size: 16pt; color: white; background-color: blue; border-radius: 50%; width: 30px; height: 30px; text-align: center; line-height: 30px; font-weight: bold;">{etape["ordre"]}</div>')
        ).add_to(carte)
    
    st_folium(carte, width=700, height=500)
    
    # Graphique Timeline
    st.subheader("📊 Timeline de la tournée")
    
    fig = go.Figure()
    
    for etape in tournee[:-1]:
        heure_arr = datetime.strptime(etape['heure_arrivee'], "%H:%M")
        heure_dep = datetime.strptime(etape['heure_depart'], "%H:%M")
        
        fig.add_trace(go.Bar(
            x=[etape['client']['nom']],
            y=[(heure_dep - heure_arr).seconds / 60],
            name=etape['client']['nom'],
            text=f"{etape['heure_arrivee']} - {etape['heure_depart']}",
            textposition='auto'
        ))
    
    fig.update_layout(
        title="Durée par livraison (minutes)",
        xaxis_title="Clients",
        yaxis_title="Minutes",
        showlegend=False,
        height=400
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Export
    st.subheader("📥 Export")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # CSV
        df = pd.DataFrame([
            {
                'Ordre': e['ordre'],
                'Client': e['client']['nom'],
                'Adresse': e['client'].get('adresse_formatee', ''),
                'Distance (km)': f"{e['distance_km']:.1f}",
                'Durée trajet (min)': e['duree_trajet_min'],
                'Heure arrivée': e['heure_arrivee'],
                'Heure départ': e.get('heure_depart', '')
            } for e in tournee
        ])
        
        csv = df.to_csv(index=False).encode('utf-8')
        
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
        for etape in tournee[:-1]:
            waypoints.append(f"{etape['client']['lat']},{etape['client']['lng']}")
        waypoints.append(f"{st.session_state.depot['lat']},{st.session_state.depot['lng']}")
        
        gmaps_url = f"https://www.google.com/maps/dir/{'/'.join(waypoints)}"
        st.link_button("🗺️ Ouvrir dans Google Maps", gmaps_url, use_container_width=True)
    
    with col3:
        if st.button("🔄 Nouvelle tournée", use_container_width=True, type="primary"):
            st.session_state.etape = 1
            st.session_state.clients = []
            st.session_state.depot = None
            st.session_state.vehicule = None
            st.session_state.tournee_optimisee = None
            st.rerun()
    
    col_back1, col_back2 = st.columns([1, 5])
    with col_back1:
        if st.button("← Modifier clients", use_container_width=True):
            st.session_state.tournee_optimisee = None
            st.session_state.etape = 3
            st.rerun()

st.markdown("---")
st.caption("💡 Application développée pour l'optimisation de tournées en Suisse · Véhicules : Camion (+20% temps) / Voiture")
