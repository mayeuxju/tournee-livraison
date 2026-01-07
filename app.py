import streamlit as st
import googlemaps
from streamlit_folium import folium_static
import folium
from datetime import datetime, timedelta
import polyline
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# --- CONFIGURATION & STYLE ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

st.markdown("""
    <style>
    .summary-box { padding: 6px 12px; border-radius: 8px; margin-bottom: 5px; display: flex; align-items: center; color: white; font-size: 0.9rem; }
    .depot-box { background-color: #28a745; border: 1px solid #1e7e34; } 
    .client-box { background-color: #0047AB; border: 1px solid #003380; }
    .client-box-force { background-color: #d9534f; border: 1px solid #cc3933; } /* Nouvelle couleur pour ramasse forcée */
    [data-testid="stHorizontalBlock"] { align-items: center; }
    .client-card { background-color: #0047AB; color: white; padding: 15px; border-radius: 10px 10px 0 0; margin-top: 10px; }
    .client-card-force { background-color: #d9534f; color: white; padding: 15px; border-radius: 10px 10px 0 0; margin-top: 10px; } /* Nouvelle couleur pour ramasse forcée */
    .address-box { background-color: #0047AB; padding: 0 15px 10px 15px; border-radius: 0 0 10px 10px; margin-bottom: 10px; }
    .address-box-force { background-color: #d9534f; padding: 0 15px 10px 15px; border-radius: 0 0 10px 10px; margin-bottom: 10px; } /* Nouvelle couleur pour ramasse forcée */
    .address-box code { color: white !important; background-color: transparent !important; font-size: 0.8rem;}
    .stExpanderHeader { background-color: #0047AB; color: white; padding: 10px; border-radius: 5px; font-weight: bold;}
    .stExpanderContent { background-color: #f8f9fa; padding: 15px; border-radius: 0 0 5px 5px;}
    .stButton>button { width: 100%; }
    .stTextInput>div>div>input { font-size: 0.9rem; }
    .stNumberInput>div>div>input { font-size: 0.9rem; }
    .stSelectbox>div>div>div { font-size: 0.9rem; }
    .stTimeInput>div>div>input { font-size: 0.9rem; }
    h2 { color: #0047AB; }
    h3 { color: #0047AB; }
    </style>
""", unsafe_allow_html=True)

# --- Initialisation des variables de session ---
if 'step' not in st.session_state:
    st.session_state.step = 1
if 'depot' not in st.session_state:
    st.session_state.depot = None
if 'clients' not in st.session_state:
    st.session_state.clients = []
if 'gmaps_client' not in st.session_state:
    st.session_state.gmaps_client = None

# Clé API Google Maps
# Assurez-vous que votre clé API est bien configurée dans secrets.toml
# [google]
# api_key="VOTRE_CLE_API_GOOGLE_MAPS"
try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
    st.session_state.gmaps_client = gmaps
except Exception as e:
    st.error(f"Erreur lors de l'initialisation de l'API Google Maps : {e}")
    st.error("Veuillez vérifier votre clé API dans le fichier secrets.toml")
    st.stop()

geolocator = Nominatim(user_agent="livreur_pro_app")

# --- Fonctions Utilitaires ---
def get_coordinates(address, geolocator_instance):
    try:
        location = geolocator_instance.geocode(address, timeout=10)
        if location:
            return location.latitude, location.longitude
        else:
            return None, None
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        st.warning(f"Problème de géolocalisation pour '{address}': {e}. Réessayez.")
        return None, None
    except Exception as e:
        st.error(f"Erreur inattendue lors de la géolocalisation de '{address}': {e}")
        return None, None

def get_full_address(lat, lng, geolocator_instance):
    try:
        location = geolocator_instance.reverse((lat, lng), exactly_one=True, timeout=10)
        if location:
            return location.address
        else:
            return "Adresse non trouvée"
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        st.warning(f"Problème de géolocalisation inverse pour ({lat}, {lng}): {e}. Réessayez.")
        return "Erreur de géolocalisation"
    except Exception as e:
        st.error(f"Erreur inattendue lors de la géolocalisation inverse de ({lat}, {lng}): {e}")
        return "Erreur inattendue"

def calculate_route(origin_coords, destination_coords, waypoints, mode="driving", departure_time="now"):
    if not origin_coords or not destination_coords:
        return None, None
    
    try:
        directions_result = gmaps.directions(origin_coords, destination_coords,
                                             mode=mode,
                                             departure_time=departure_time,
                                             waypoints=waypoints,
                                             optimize_waypoints=False) # On optimise nous-même
        if not directions_result:
            return None, None

        route = directions_result[0]
        
        # Calculer les coordonnées des points intermédiaires pour la carte
        leg_coords = []
        if route['legs']:
            # Leg du dépôt aux premiers points
            leg_coords.extend(polyline.decode(route['legs'][0]['steps'][0]['polyline']['points']) if route['legs'][0]['steps'] else [])

            # Legs entre les points
            for i in range(len(route['legs']) - 1):
                for step in route['legs'][i]['steps']:
                    leg_coords.extend(polyline.decode(step['polyline']['points']))
            
            # Leg final
            if route['legs'][-1]['steps']:
                 for step in route['legs'][-1]['steps']:
                    leg_coords.extend(polyline.decode(step['polyline']['points']))

        # Pour avoir une polyligne unique pour le trajet total
        full_polyline = ""
        if route['overview_polyline']:
            full_polyline = route['overview_polyline']['points']

        return leg_coords, full_polyline

    except googlemaps.exceptions.ApiError as e:
        st.error(f"Erreur API Google Maps : {e}")
        return None, None
    except Exception as e:
        st.error(f"Erreur lors du calcul de l'itinéraire : {e}")
        return None, None

def calculate_optimised_route(origin_coords, destination_coords, waypoints_dict, mode="driving", departure_time=None):
    if not origin_coords or not waypoints_dict:
        return None, None, None

    # Préparer les waypoints pour Google Maps API
    waypoint_list_for_api = []
    ordered_clients_info = []
    
    # Séparer livraisons et ramasses, et gérer les ramasses forcées
    livraisons = []
    ramasses = []
    ramasses_forcees = []

    for client_data in waypoints_dict:
        if client_data['type'] == 'Livraison':
            livraisons.append(client_data)
        elif client_data['type'] == 'Ramasse':
            if client_data.get('force_aller', False): # Gérer la nouvelle option
                ramasses_forcees.append(client_data)
            else:
                ramasses.append(client_data)
    
    # Logique d'ordonnancement :
    # 1. Aller : Dépôt -> Livraisons + Ramasses Forcées (triées géographiquement si possible)
    # 2. Retour : Ramasses (triées géographiquement en sens inverse) -> Dépôt

    # Utiliser la logique "Logique Chauffeur" comme base
    
    # Calculer l'itinéraire optimal pour les livraisons et ramasses forcées
    allers = livraisons + ramasses_forcees
    
    if not allers: # Si pas de livraisons ou ramasses forcées, on peut potentiellement aller direct aux ramasses si elles existent
        final_order_dict = ramasses
        final_order_dict.sort(key=lambda x: x['distance_from_depot'], reverse=True) # Sortir les ramasses du plus loin au plus près
    else:
        # Si on a des allers, on utilise l'optimisation par défaut de Google pour ceux-ci.
        # Pour une vraie optimisation sur un grand nombre de points, il faudrait une librairie comme OR-Tools ou une approche heuristique.
        # Ici, on va juste trier par distance pour une approximation simple.
        for c in allers:
            c['distance_from_depot'] = geodesic(origin_coords, (c['lat'], c['lng'])).km
        allers.sort(key=lambda x: x['distance_from_depot'])

        # Préparer la liste pour l'API Google Maps (pour les livraisons et ramasses forcées)
        for client in allers:
            waypoint_list_for_api.append((client['lat'], client['lng']))
            ordered_clients_info.append(client)

        # Les ramasses non forcées seront ajoutées à la fin du trajet
        # On les trie du plus loin au plus près du dépôt pour le retour
        for client in ramasses:
            client['distance_from_depot'] = geodesic(origin_coords, (client['lat'], client['lng'])).km
        ramasses.sort(key=lambda x: x['distance_from_depot'], reverse=True)

        # Ajouter les ramasses non forcées à la fin de notre liste ordonnée
        for client in ramasses:
            waypoint_list_for_api.append((client['lat'], client['lng']))
            ordered_clients_info.append(client)

    # Si on n'a pas spécifié de destination explicite, on utilise le dernier point de la tournée comme destination
    destination_coords = (ordered_clients_info[-1]['lat'], ordered_clients_info[-1]['lng']) if ordered_clients_info else origin_coords

    # Appel à Google Maps Directions API
    try:
        # Pour l'optimisation, il faut passer les waypoints (tous les clients sauf dépôt et destination finale)
        # Google peut réordonner ces waypoints si optimize_waypoints=True
        # Comme on a déjà fait un tri manuel, on laisse optimize_waypoints=False
        
        # Construire le chemin complet : Dépôt -> Points -> Dépôt (si nécessaire)
        # Pour simplifier, on va faire Dépôt -> Tous les points
        
        # Si on a des points, la destination finale est le dernier point ordonné.
        # Sinon, c'est le dépôt lui-même.
        
        if not ordered_clients_info:
            return None, None, None # Pas de points à visiter

        # Les 'waypoints' doivent exclure l'origine et la destination finale
        # Ici, on passe tous les points à visiter comme waypoints, et le dernier comme destination
        
        # Il est plus simple de laisser Google optimiser si on ne fait pas de tri manuel poussé
        # Si on veut le tri manuel Livraisons/Ramasses :
        # On demande le trajet Dépôt -> Dernier point, en passant par tous les autres dans l'ordre calculé.
        
        final_waypoints_for_api = waypoint_list_for_api[:-1] if len(waypoint_list_for_api) > 1 else []
        final_destination = waypoint_list_for_api[-1] if waypoint_list_for_api else origin_coords

        if not final_waypoints_for_api and len(waypoint_list_for_api) == 1: # Cas d'un seul point
            final_waypoints_for_api = []
            final_destination = waypoint_list_for_api[0]
        elif not final_waypoints_for_api and not waypoint_list_for_api: # Cas aucun point
             return None, None, None

        directions_result = gmaps.directions(origin_coords, final_destination,
                                             mode=mode,
                                             departure_time=departure_time,
                                             waypoints=final_waypoints_for_api,
                                             optimize_waypoints=False) # On a déjà fait notre optimisation manuelle

        if not directions_result:
            return None, None, None

        route = directions_result[0]
        
        # Extraire le polyline pour la carte
        full_polyline = route['overview_polyline']['points']
        
        # Construire la liste des points ordonnés avec les temps d'arrivée et de départ simulés
        simulated_stops = []
        current_time = departure_time if isinstance(departure_time, datetime) else datetime.now() # Si depart_time est 'now', utiliser datetime.now()

        # Dépôt de départ
        simulated_stops.append({
            'nom': st.session_state.depot['nom'],
            'lat': origin_coords[0],
            'lng': origin_coords[1],
            'arrival_time': None, # Pas d'heure d'arrivée au dépôt de départ
            'departure_time': current_time,
            'full_address': st.session_state.depot['full_address'],
            'type': 'Dépôt',
            'dur': 0, # Durée de visite au dépôt de départ
            'contrainte': None,
            'force_aller': False
        })

        # Parcourir les legs et les points ordonnés
        leg_index = 0
        client_index = 0 # Index dans ordered_clients_info

        # Traiter le premier leg (Dépôt -> 1er waypoint)
        if route['legs']:
            first_leg = route['legs'][0]
            
            # Heure d'arrivée au premier point
            arrival_at_first_point = current_time + timedelta(seconds=first_leg['duration_in_traffic']['value'])
            
            current_client = ordered_clients_info[client_index]
            
            # Vérifier et ajuster pour les contraintes horaires
            window_start_time = None
            window_end_time = None
            if current_client.get('heure_debut') and current_client.get('heure_fin'):
                # Combiner date de départ avec heures spécifiées
                window_start_time = datetime.combine(departure_time.date(), current_client['heure_debut']) if isinstance(departure_time, datetime) else datetime.combine(datetime.now().date(), current_client['heure_debut'])
                window_end_time = datetime.combine(departure_time.date(), current_client['heure_fin']) if isinstance(departure_time, datetime) else datetime.combine(datetime.now().date(), current_client['heure_fin'])

                # Si l'arrivée est avant l'ouverture, on attend
                if arrival_at_first_point < window_start_time:
                    wait_time = window_start_time - arrival_at_first_point
                    arrival_at_first_point = window_start_time # On arrive à l'heure d'ouverture
                    # On met à jour le temps de départ pour inclure l'attente
                    current_time = arrival_at_first_point # Le temps de départ sera après l'attente
                
                # Vérifier si on arrive trop tard
                if arrival_at_first_point > window_end_time:
                    current_client['alerte'] = "Trop tard !"
            
            departure_from_current_point = arrival_at_first_point + timedelta(minutes=current_client['dur'])
            
            current_client['arrival_time'] = arrival_at_first_point
            current_client['departure_time'] = departure_from_current_point
            current_client['full_address'] = get_full_address(current_client['lat'], current_client['lng'], geolocator) # Compléter l'adresse si besoin
            
            simulated_stops.append(current_client)
            current_time = departure_from_current_point # Le temps de départ de ce point devient le temps d'arrivée au prochain
            client_index += 1
            leg_index += 1
        
        # Traiter les legs intermédiaires (Waypoint N -> Waypoint N+1)
        while leg_index < len(route['legs']) -1:
            current_leg = route['legs'][leg_index]
            arrival_at_next_point = current_time + timedelta(seconds=current_leg['duration_in_traffic']['value'])
            
            current_client = ordered_clients_info[client_index]
            
            # Vérifier et ajuster pour les contraintes horaires
            window_start_time = None
            window_end_time = None
            if current_client.get('heure_debut') and current_client.get('heure_fin'):
                window_start_time = datetime.combine(departure_time.date(), current_client['heure_debut']) if isinstance(departure_time, datetime) else datetime.combine(datetime.now().date(), current_client['heure_debut'])
                window_end_time = datetime.combine(departure_time.date(), current_client['heure_fin']) if isinstance(departure_time, datetime) else datetime.combine(datetime.now().date(), current_client['heure_fin'])

                if arrival_at_next_point < window_start_time:
                    wait_time = window_start_time - arrival_at_next_point
                    arrival_at_next_point = window_start_time
                    current_time = arrival_at_next_point # Le temps de départ sera après l'attente
                
                if arrival_at_next_point > window_end_time:
                    current_client['alerte'] = "Trop tard !"

            departure_from_current_point = arrival_at_next_point + timedelta(minutes=current_client['dur'])
            
            current_client['arrival_time'] = arrival_at_next_point
            current_client['departure_time'] = departure_from_current_point
            current_client['full_address'] = get_full_address(current_client['lat'], current_client['lng'], geolocator)
            
            simulated_stops.append(current_client)
            current_time = departure_from_current_point
            client_index += 1
            leg_index += 1
        
        # Traiter le dernier leg (Avant dernier point -> Destination finale)
        if leg_index < len(route['legs']): # S'il y a un dernier leg (même si destination = dernier waypoint)
            last_leg = route['legs'][leg_index]
            arrival_at_final_destination = current_time + timedelta(seconds=last_leg['duration_in_traffic']['value'])
            
            # La destination finale est le dernier point ordonné
            current_client = ordered_clients_info[client_index]

            # Vérifier et ajuster pour les contraintes horaires si c'est aussi un point client
            window_start_time = None
            window_end_time = None
            if current_client.get('heure_debut') and current_client.get('heure_fin'):
                window_start_time = datetime.combine(departure_time.date(), current_client['heure_debut']) if isinstance(departure_time, datetime) else datetime.combine(datetime.now().date(), current_client['heure_debut'])
                window_end_time = datetime.combine(departure_time.date(), current_client['heure_fin']) if isinstance(departure_time, datetime) else datetime.combine(datetime.now().date(), current_client['heure_fin'])

                if arrival_at_final_destination < window_start_time:
                    wait_time = window_start_time - arrival_at_final_destination
                    arrival_at_final_destination = window_start_time
                    current_time = arrival_at_final_destination
                
                if arrival_at_final_destination > window_end_time:
                    current_client['alerte'] = "Trop tard !"
            
            # La durée de visite est toujours appliquée même à la destination finale si c'est un client
            departure_from_final_destination = arrival_at_final_destination + timedelta(minutes=current_client['dur'])
            
            current_client['arrival_time'] = arrival_at_final_destination
            current_client['departure_time'] = departure_from_final_destination
            current_client['full_address'] = get_full_address(current_client['lat'], current_client['lng'], geolocator)
            
            simulated_stops.append(current_client)
            current_time = departure_from_final_destination
            client_index += 1

        # Si le dernier point était une ramasse, on peut le considérer comme la fin du trajet
        # Si on a un retour au dépôt à simuler, il faut ajuster
        # Pour l'instant, on s'arrête au dernier point client.
        # Si on veut simuler un retour au dépôt :
        # Il faudrait ajouter le dépôt comme dernière destination s'il n'est pas déjà le dernier point.
        # Et calculer le temps de trajet Dépôt_final -> Dépôt_origine.

        # Ajouter le retour au dépôt s'il n'est pas déjà la destination
        if final_destination != origin_coords:
            final_leg_to_depot = gmaps.directions(final_destination, origin_coords, mode=mode, departure_time=current_time)
            if final_leg_to_depot:
                time_to_depot = timedelta(seconds=final_leg_to_depot[0]['legs'][0]['duration_in_traffic']['value'])
                arrival_at_depot = current_time + time_to_depot
                simulated_stops.append({
                    'nom': st.session_state.depot['nom'],
                    'lat': origin_coords[0],
                    'lng': origin_coords[1],
                    'arrival_time': arrival_at_depot,
                    'departure_time': arrival_at_depot, # Fin de tournée
                    'full_address': st.session_state.depot['full_address'],
                    'type': 'Dépôt',
                    'dur': 0,
                    'contrainte': None,
                    'force_aller': False
                })
        
        # Assurez-vous que tous les clients sont bien dans simulated_stops
        # Si un client n'est pas dans simulated_stops, c'est qu'il y a un souci dans le parcours
        
        return full_polyline, simulated_stops, ordered_clients_info # ordered_clients_info est la liste de clients dans l'ordre de passage

    except googlemaps.exceptions.ApiError as e:
        st.error(f"Erreur API Google Maps : {e}")
        return None, None, None
    except Exception as e:
        st.error(f"Erreur lors du calcul de l'itinéraire optimisé : {e}")
        return None, None, None

# --- Interface Utilisateur ---

# Étape 1: Saisie du dépôt et des clients
if st.session_state.step == 1:
    st.title("🚗 Planificateur de Tournée Professionnelle")
    st.subheader("Étape 1 : Définir le Dépôt et les Arrêts")

    with st.form("depot_form", clear_on_submit=True):
        st.markdown("### 🏡 Dépôt de départ")
        depot_nom = st.text_input("Nom du dépôt", "Mon Dépôt Principal")
        depot_adresse = st.text_input("Adresse complète du dépôt", placeholder="Ex: Rue de la Gare 1, 1000 Lausanne")
        depot_heure_debut = st.time_input("Heure de départ", datetime.combine(datetime.now().date(), datetime(1900, 1, 1, 8, 0)).time())

        submitted_depot = st.form_submit_button("Enregistrer le dépôt et passer aux arrêts")

        if submitted_depot and depot_adresse:
            depot_lat, depot_lng = get_coordinates(depot_adresse, geolocator)
            if depot_lat and depot_lng:
                st.session_state.depot = {
                    "nom": depot_nom,
                    "adresse": depot_adresse,
                    "lat": depot_lat,
                    "lng": depot_lng,
                    "heure_debut": depot_heure_debut,
                    "full_address": get_full_address(depot_lat, depot_lng, geolocator)
                }
                st.success("Dépôt enregistré !")
            else:
                st.error("Impossible de géolocaliser l'adresse du dépôt. Veuillez vérifier.")
        elif submitted_depot and not depot_adresse:
            st.error("Veuillez entrer une adresse pour le dépôt.")

    if st.session_state.depot:
        st.markdown(f"**Dépôt :** {st.session_state.depot['nom']} - {st.session_state.depot['adresse']} (Départ à {st.session_state.depot['heure_debut'].strftime('%H:%M')})")
        
        st.markdown("### 📍 Ajouter un Arrêt")
        with st.form("client_form", clear_on_submit=True):
            client_nom = st.text_input("Nom du client / Point d'intérêt", placeholder="Ex: Client A, Bureau X")
            # Champs d'adresse séparés et flexibles
            col1, col2, col3 = st.columns(3)
            client_rue = col1.text_input("Rue et N°", placeholder="Ex: Avenue des Champs 12")
            client_npa = col2.text_input("NPA", placeholder="Ex: 1000", max_chars=5)
            client_ville = col3.text_input("Ville", placeholder="Ex: Lausanne")
            
            client_type = st.selectbox("Type d'opération", ["Livraison", "Ramasse"])
            # Nouvelle case à cocher pour forcer la ramasse à l'aller
            force_aller = st.checkbox("Forcer ce point à l'aller (même si Ramasse)", disabled=(client_type == "Livraison"))

            col_horaire, col_duree = st.columns(2)
            client_heure_debut = col_horaire.time_input("Fenêtre de passage (Début)", value=None, key="client_heure_debut_opt")
            client_heure_fin = col_horaire.time_input("Fenêtre de passage (Fin)", value=None, key="client_heure_fin_opt")
            client_duree = col_duree.number_input("Durée estimée de la visite (min)", min_value=1, value=15, step=1)

            submitted_client = st.form_submit_button("Ajouter l'arrêt")

            if submitted_client and client_nom and client_rue and client_npa and client_ville:
                full_address = f"{client_rue}, {client_npa} {client_ville}"
                client_lat, client_lng = get_coordinates(full_address, geolocator)
                
                if client_lat and client_lng:
                    client_data = {
                        "nom": client_nom,
                        "rue": client_rue,
                        "npa": client_npa,
                        "ville": client_ville,
                        "full_address": full_address,
                        "lat": client_lat,
                        "lng": client_lng,
                        "type": client_type,
                        "heure_debut": client_heure_debut,
                        "heure_fin": client_heure_fin,
                        "dur": client_duree,
                        "force_aller": force_aller if client_type == "Ramasse" else False,
                        "alerte": None # Pour les alertes futures (ex: trop tard)
                    }
                    st.session_state.clients.append(client_data)
                    st.success(f"Arrêt '{client_nom}' ajouté !")
                else:
                    st.error(f"Impossible de géolocaliser l'adresse '{full_address}'. Vérifiez et réessayez.")
            elif submitted_client:
                st.error("Veuillez remplir tous les champs d'adresse (Rue, NPA, Ville) et le nom du client.")

    # Affichage de la liste des clients ajoutés
    if st.session_state.clients:
        st.subheader("Liste des arrêts programmés")
        
        # Trier les clients pour un affichage plus logique dans la liste
        # D'abord les livraisons, puis les ramasses
        clients_a_afficher = sorted(st.session_state.clients, key=lambda x: (x['type'] != 'Livraison', x['nom']))
        
        cols_display = st.columns([1, 3, 2, 1, 1, 1]) # Nom, Adresse, Type, Contrainte, Durée, Boutons
        cols_display[0].write("**Nom**")
        cols_display[1].write("**Adresse**")
        cols_display[2].write("**Type**")
        cols_display[3].write("**Fenêtre Passage**")
        cols_display[4].write("**Durée**")
        cols_display[5].write("**Action**")

        for i, client in enumerate(clients_a_afficher):
            col1, col2, col3, col4, col5, col6 = st.columns([1, 3, 2, 1, 1, 1])
            
            col1.write(client['nom'])
            col2.write(client['full_address'])
            
            type_display = client['type']
            is_forced = client.get('force_aller', False) and client['type'] == 'Ramasse'
            
            if is_forced:
                col3.markdown(f"<span style='background-color: #d9534f; color: white; padding: 3px 6px; border-radius: 5px;'>{type_display} (Aller Forcé)</span>", unsafe_allow_html=True)
            else:
                col3.markdown(f"<span style='background-color: {'#007bff' if client_type == 'Livraison' else '#6c757d'}; color: white; padding: 3px 6px; border-radius: 5px;'>{type_display}</span>", unsafe_allow_html=True)
            
            # Affichage des contraintes horaire et durée
            contrainte_str = ""
            if client.get('heure_debut') and client.get('heure_fin'):
                contrainte_str = f"{client['heure_debut'].strftime('%H:%M')} - {client['heure_fin'].strftime('%H:%M')}"
            col4.write(contrainte_str)
            col5.write(f"{client['dur']} min")

            # Boutons pour éditer ou supprimer
            if col6.button("✏️", key=f"edit_{i}"):
                # On va passer à l'étape d'édition
                st.session_state.edit_index = i
                st.session_state.step = 2 # Aller à l'étape d'édition/calcul
                st.rerun() # Rafraîchir pour changer d'étape

            if col6.button("🗑️", key=f"delete_{i}"):
                # Supprimer le client
                st.session_state.clients.pop(i) # Supprime directement de la liste originale
                st.rerun() # Rafraîchir pour mettre à jour la liste

    if st.session_state.depot and st.session_state.clients:
        if st.button("🚀 Lancer l'Optimisation", key="launch_optimization"):
            st.session_state.step = 2
            st.rerun()

# Étape 2: Affichage de la carte et des détails de la tournée
elif st.session_state.step == 2:
    st.title("🗺️ Votre Tournée Optimisée")
    st.subheader("Résultats de l'Optimisation")

    if not st.session_state.depot or not st.session_state.clients:
        st.warning("Veuillez d'abord définir le dépôt et les arrêts.")
        if st.button("Retour à l'Étape 1", key="back_to_step1_from_step2"):
            st.session_state.step = 1
            st.rerun()
        st.stop()

    depot_coords = (st.session_state.depot['lat'], st.session_state.depot['lng'])
    depot_departure_time_dt = datetime.combine(datetime.now().date(), st.session_state.depot['heure_debut'])

    # --- Choix du mode d'optimisation ---
    mode_optimisation = st.selectbox("Mode d'Optimisation", 
                                     ["Logique Chauffeur (Aller Livraisons -> Retour Ramasses)", 
                                      "Mathématique (Itinéraire le plus court, sans distinction type)",
                                      "Priorité Horaire (Moins d'attente, puis Livraisons -> Ramasses)"],
                                     key="mode_optimisation_select")

    # Préparation des données pour le calcul
    waypoints_data = []
    for client in st.session_state.clients:
        # Pour le calcul d'itinéraire, on a besoin des coordonnées et de la durée
        waypoint_info = {
            'nom': client['nom'],
            'lat': client['lat'],
            'lng': client['lng'],
            'dur': client['dur'],
            'type': client['type'],
            'heure_debut': client['heure_debut'],
            'heure_fin': client['heure_fin'],
            'force_aller': client.get('force_aller', False)
        }
        waypoints_data.append(waypoint_info)

    # Calcul de l'itinéraire basé sur le mode choisi
    full_route_polyline = None
    simulated_stops = None
    ordered_clients_for_display = None # Liste ordonnée des clients passés à l'algo
    
    # On utilise ici la fonction calculate_optimised_route
    # La logique de tri sera appliquée DANS cette fonction.
    
    # Préparer les clients pour calculate_optimised_route
    # On passe la liste complète, la fonction triera
    
    # --- LOGIQUE D'OPTIMISATION SPÉCIFIQUE ---
    
    final_ordered_clients = []
    
    if mode_optimisation == "Mathématique (Itinéraire le plus court, sans distinction type)":
        # Pour le mode mathématique, on demande à Google de réordonner les points
        # Il faut donc passer tous les points comme waypoints à optimiser.
        # On va construire un itinéraire Dépôt -> Tous les points (optimisés par Google)
        
        # On prend tous les clients et le dépôt comme points de passage
        all_points_for_gmaps = [depot_coords] + [(c['lat'], c['lng']) for c in st.session_state.clients]
        
        if len(all_points_for_gmaps) > 2: # Plus de 2 points (dépôt + au moins 1 client)
            directions_result = gmaps.directions(depot_coords, all_points_for_gmaps[-1], # Dépôt -> Dernier point
                                                 mode="driving",
                                                 departure_time=depot_departure_time_dt,
                                                 waypoints=all_points_for_gmaps[1:-1], # Tous les clients intermédiaires
                                                 optimize_waypoints=True) # C'est ici que Google optimise
            
            if directions_result:
                route_info = directions_result[0]
                ordered_waypoint_indices = route_info['waypoint_order'] # Indices de réordonnancement
                
                # Reconstruction de la liste des clients dans le nouvel ordre
                temp_ordered_clients = []
                # Le premier point est le dépôt
                temp_ordered_clients.append(st.session_state.depot)
                
                # Ajouter les clients dans l'ordre optimisé par Google
                for index in ordered_waypoint_indices:
                    # Il faut retrouver le client correspondant à cet index
                    # L'index dans 'ordered_waypoint_indices' correspond à l'ordre dans la liste passée à 'waypoints'
                    # donc si clients = [C1, C2, C3], index 0 dans ordered_waypoint_indices = C1, index 1 = C2 etc.
                    # MAIS attention si le dernier point était déjà la destination finale.
                    
                    # Il est plus simple de mapper l'index de google aux clients originaux
                    # L'ordre des 'waypoints' dans l'appel API est : all_points_for_gmaps[1:-1]
                    # Donc ordered_waypoint_indices[i] donne l'index original dans cette liste 'waypoints'
                    
                    original_client_list = st.session_state.clients # La liste non triée
                    
                    # Si le dernier point est un client (donc destination finale n'est pas le dépôt)
                    # L'ordre de google est Dépôt -> Optimisé -> Dernier point.
                    # La liste des waypoints passés était : clients[0], clients[1] ... clients[N-1]
                    # Google a réordonné ces indices.
                    
                    # On va plutôt réordonner la liste 'st.session_state.clients' elle-même.
                    ordered_indices = route_info['waypoint_order']
                    
                    # Créer une nouvelle liste ordonnée
                    ordered_clients_in_step2 = [st.session_state.clients[i] for i in ordered_indices]
                    
                    # Assurer que le dernier point (destination) est bien pris en compte si ce n'est pas un waypoint
                    # Si la destination finale de l'API était le dernier client de la liste `all_points_for_gmaps`
                    # alors ce client est le dernier point de la tournée.
                    # Il faut s'assurer qu'il est bien à la fin de `ordered_clients_in_step2`
                    
                    # Pour simplifier, on va simuler les temps d'arrivée sur la base de cet ordre
                    # et de la route calculée.

                    # On va reconstruire le parcours client par client
                    # On utilise la route calculée et les indices ordonnés
                    # La liste `ordered_waypoint_indices` contient les indices du tableau `all_points_for_gmaps[1:-1]` qui sont les waypoints.
                    # Si `all_points_for_gmaps` est [Dépôt, C1, C2, C3] et que la destination est C3
                    # `waypoints` = [C1, C2]
                    # `optimize_waypoints=True` retourne un `waypoint_order` comme [1, 0]. Cela signifie :
                    # Ordre : Dépôt -> C2 -> C1 -> C3.
                    
                    # On va refaire le calcul de simulation de temps basé sur cet ordre.
                    # Pour éviter de dupliquer la logique, on va reformater les données et réutiliser calculate_optimised_route
                    # Il faut créer une liste de clients dans l'ordre GIVEN by Google Maps API
                    
                    # On map les indices retournés par Google à la liste originale `st.session_state.clients`
                    
                    final_ordered_clients_math = []
                    
                    # Créez une liste temporaire de tuples (index_original, client_data)
                    clients_with_original_indices = list(enumerate(st.session_state.clients))
                    
                    # Si le dernier point de `all_points_for_gmaps` est différent du dépôt, c'est le client final
                    is_last_point_a_client = (all_points_for_gmaps[-1] != depot_coords)
                    
                    # Construire la liste des points DANS L'ORDRE GIVEN BY GOOGLE
                    # Les waypoints sont ordonnés par `ordered_waypoint_indices`
                    for idx in ordered_waypoint_indices:
                        # L'index `idx` ici est l'index dans la liste `waypoints` passée à l'API.
                        # Dans notre cas `waypoints` = `all_points_for_gmaps[1:-1]`
                        # Donc l'index `idx` correspond à l'index original dans `st.session_state.clients`
                        final_ordered_clients_math.append(st.session_state.clients[idx])
                    
                    # Si le dernier point de l'itinéraire était un client et qu'il n'est pas déjà dans la liste ordonnée (car pas un waypoint)
                    if is_last_point_a_client:
                        # Le dernier point de `all_points_for_gmaps` est `all_points_for_gmaps[-1]`.
                        # Il faut vérifier si ce point correspond au dernier client de `st.session_state.clients`.
                        # Si c'est le cas, et qu'il n'est pas déjà dans `final_ordered_clients_math`, on l'ajoute.
                        
                        # Une façon plus simple : Google retourne l'ordre des WAYPOINTS. Le point de DÉPART et de DESTINATION sont fixes.
                        # Si `directions` est appelé avec `origin`, `destination`, `waypoints`, `optimize_waypoints=True`.
                        # `route['waypoint_order']` donne l'ordre des `waypoints`.
                        # `route['legs']` donne les segments entre :
                        # Leg 0: origin -> waypoint[waypoint_order[0]]
                        # Leg 1: waypoint[waypoint_order[0]] -> waypoint[waypoint_order[1]]
                        # ...
                        # Leg N: waypoint[waypoint_order[N-1]] -> destination
                        
                        # On doit reconstruire l'ordre complet : Origin -> Waypoints (ordonnés) -> Destination
                        
                        ordered_waypoint_coords = [all_points_for_gmaps[i+1] for i in ordered_waypoint_indices] # +1 car on saute le depot
                        full_ordered_path_coords = [depot_coords] + ordered_waypoint_coords + [all_points_for_gmaps[-1]] # Si le dernier point est un client

                        # Assurez-vous que les coordonnées correspondent aux clients originaux
                        ordered_clients_for_math_mode = []
                        
                        # Le dépôt de départ
                        ordered_clients_for_math_mode.append(st.session_state.depot)
                        
                        # Les waypoints dans leur nouvel ordre
                        for wp_coord in ordered_waypoint_coords:
                            for client in st.session_state.clients:
                                if (client['lat'], client['lng']) == wp_coord:
                                    ordered_clients_for_math_mode.append(client)
                                    break
                        
                        # Le point de destination final (si différent du dépôt et du dernier waypoint)
                        # Google le gère dans la route, on doit juste s'assurer que le dernier client est là
                        if all_points_for_gmaps[-1] != depot_coords and all_points_for_gmaps[-1] not in ordered_waypoint_coords:
                             for client in st.session_state.clients:
                                if (client['lat'], client['lng']) == all_points_for_gmaps[-1]:
                                    ordered_clients_for_math_mode.append(client)
                                    break
                        
                        # On réutilise calculate_optimised_route avec les données filtrées pour le mode math
                        # Il faut le faire de manière à ce que calculate_optimised_route soit appelée une seule fois
                        # Donc il faut préparer les inputs pour calculate_optimised_route en fonction du mode
                        
                        # Créer une liste `current_all_clients_data` qui contient les clients dans l'ordre voulu pour ce mode
                        current_all_clients_data = ordered_clients_for_math_mode[1:] # On retire le dépôt de cette liste
                        
                        # On doit aussi reconstruire la liste `ordered_clients_info` qui contient le détail client
                        # Pour ce mode, `ordered_clients_info` sera donc `ordered_clients_for_math_mode[1:]`
                        
                        # Appel final
                        full_route_polyline, simulated_stops, ordered_clients_for_display = calculate_optimised_route(
                            depot_coords, 
                            all_points_for_gmaps[-1], # Destination finale
                            current_all_clients_data, # Liste de clients à visiter
                            mode="driving",
                            departure_time=depot_departure_time_dt
                        )
                        
                        # Si la destination finale est le dépôt, on doit adapter la simulation
                        if all_points_for_gmaps[-1] == depot_coords:
                            full_route_polyline, simulated_stops, ordered_clients_for_display = calculate_optimised_route(
                                depot_coords, 
                                depot_coords, # Destination est le dépôt
                                current_all_clients_data, # Liste de clients à visiter
                                mode="driving",
                                departure_time=depot_departure_time_dt
                            )

                else:
                    st.error("Impossible d'obtenir la route optimisée par Google.")
            
        else: # Moins de 2 points, pas besoin d'optimisation complexe
             full_route_polyline, simulated_stops, ordered_clients_for_display = calculate_optimised_route(
                depot_coords, 
                depot_coords, # Destination = dépôt
                st.session_state.clients, 
                mode="driving",
                departure_time=depot_departure_time_dt
            )
    
    else: # Modes "Logique Chauffeur" ou "Priorité Horaire"
        # Ces modes utilisent la logique interne de `calculate_optimised_route`
        # Qui trie d'abord livraisons, puis ramasses forcées, puis ramasses normales.
        # La priorité horaire est gérée DANS `calculate_optimised_route`
        
        full_route_polyline, simulated_stops, ordered_clients_for_display = calculate_optimised_route(
            depot_coords, 
            depot_coords, # On utilise le dépôt comme destination de référence, calculate_optimised_route va le gérer
            waypoints_data, # Tous les clients avec leurs propriétés
            mode="driving",
            departure_time=depot_departure_time_dt
        )
        
        # Si le mode est "Priorité Horaire", on veut que calculate_optimised_route prenne en compte les fenêtres
        # Pour cela, il faut s'assurer que la logique dans calculate_optimised_route est bien activée
        # Notre implémentation de `calculate_optimised_route` gère déjà la priorité horaire en ajustant les temps d'arrivée.
        # Il faut juste s'assurer que le mode de calcul est bon.
        # La fonction `calculate_optimised_route` fait le tri Livraisons -> Ramasses Forcées -> Ramasses.
        # Elle calcule ensuite les temps en tenant compte des fenêtres.

    # --- Affichage des résultats ---
    if full_route_polyline and simulated_stops:
        
        # Créer une carte Folium
        m_final = folium.Map(location=depot_coords, zoom_start=12, tiles="cartopositron")
        
        # Ajouter le dépôt
        folium.Marker(depot_coords, popup=st.session_state.depot['nom'], icon=folium.Icon(color="green", icon="home")).add_to(m_final)
        
        # Ajouter les points de la tournée ordonnée
        # `simulated_stops` contient le dépôt au début et potentiellement à la fin
        # et les clients ordonnés entre eux.
        
        # Déterminer la destination finale pour la polyligne
        # Si le dernier point est un dépôt et qu'il y a plusieurs arrêts, c'est le retour au dépôt.
        # Sinon, c'est le dernier client.
        
        last_stop_coords = None
        if simulated_stops:
            last_stop_coords = (simulated_stops[-1]['lat'], simulated_stops[-1]['lng'])
            
            # Afficher les points clients
            for i, stop in enumerate(simulated_stops):
                if stop['type'] == 'Dépôt':
                    continue # Déjà ajouté
                
                # Marqueur coloré selon le type
                icon_color = "blue" # Livraison
                if stop['type'] == 'Ramasse':
                    icon_color = "orange"
                if stop.get('alerte') == "Trop tard !":
                    icon_color = "red"
                
                # Icône spécifique pour ramasse forcée (si on veut la distinguer visuellement)
                # On pourrait ajouter un symbole, mais la couleur suffira.
                
                marker_icon = folium.Icon(color=icon_color, icon="info-sign")
                if stop['type'] == 'Ramasse' and stop.get('force_aller'):
                     marker_icon = folium.Icon(color="red", icon="download") # Rouge pour forcé, icône download
                elif stop['type'] == 'Ramasse':
                     marker_icon = folium.Icon(color="orange", icon="upload") # Orange pour ramasse normale, icône upload
                elif stop['type'] == 'Livraison':
                     marker_icon = folium.Icon(color="blue", icon="box") # Bleu pour livraison

                folium.Marker([stop['lat'], stop['lng']], popup=f"{stop['nom']} ({stop['type']})", icon=marker_icon).add_to(m_final)

        # Ajouter la polyligne principale
        if full_route_polyline:
            try:
                # Décoder le polyline pour l'ajouter à la carte
                decoded_polyline = polyline.decode(full_route_polyline)
                # Pour afficher la route, on peut la diviser en segments si nécessaire
                # Si le dernier point est le dépôt, on peut colorer différemment le retour
                
                # On va simplifier : une seule polyligne pour tout le trajet.
                folium.PolyLine(decoded_polyline, color="blue", weight=5, opacity=0.7).add_to(m_final)
            except Exception as e:
                st.warning(f"Impossible d'afficher la polyligne principale : {e}")

        # Afficher la carte
        st.subheader("Carte de la Tournée")
        folium_static(m_final, width=1000)

        # Affichage de la liste détaillée des arrêts dans l'ordre calculé
        st.subheader("Détail des Arrêts")
        
        # On utilise `simulated_stops` pour l'affichage car il contient les temps calculés
        if simulated_stops:
            cols_detail = st.columns([0.5, 1, 2, 1, 1, 1, 1, 1]) # Ordre, Nom, Adresse, Type, Fenêtre, Durée, Arrivée, Départ
            cols_detail[0].write("**Ordre**")
            cols_detail[1].write("**Nom**")
            cols_detail[2].write("**Adresse**")
            cols_detail[3].write("**Type**")
            cols_detail[4].write("**Fenêtre**")
            cols_detail[5].write("**Durée Visite**")
            cols_detail[6].write("**Arrivée**")
            cols_detail[7].write("**Départ**")

            for i, stop in enumerate(simulated_stops):
                col0, col1, col2, col3, col4, col5, col6, col7 = st.columns([0.5, 1, 2, 1, 1, 1, 1, 1])
                
                col0.write(f"{i+1}.")
                col1.write(stop['nom'])
                col2.write(stop['full_address'])
                
                type_str = stop['type']
                color = "blue" # Livraison
                if stop['type'] == 'Ramasse':
                    color = "orange"
                    if stop.get('force_aller'):
                        type_str += " (Aller Forcé)"
                        color = "red" # Couleur pour forcé
                
                if stop.get('alerte'):
                    type_str += f" ⚠️ {stop['alerte']}"
                    color = "red" # Alerte > fenêtre de passage
                    
                col3.markdown(f"<span style='background-color: {color}; color: white; padding: 3px 6px; border-radius: 5px;'>{type_str}</span>", unsafe_allow_html=True)
                
                # Affichage fenêtre horaire
                window_str = ""
                if stop.get('heure_debut') and stop.get('heure_fin'):
                    window_str = f"{stop['heure_debut'].strftime('%H:%M')} - {stop['heure_fin'].strftime('%H:%M')}"
                col4.write(window_str)
                
                col5.write(f"{stop['dur']} min")
                
                # Affichage temps d'arrivée et de départ
                if stop['arrival_time']:
                    col6.write(stop['arrival_time'].strftime('%H:%M:%S'))
                else:
                    col6.write("-") # Pas d'arrivée au dépôt de départ

                if stop['departure_time']:
                    col7.write(stop['departure_time'].strftime('%H:%M:%S'))
                else:
                    col7.write("-") # Fin de tournée au dépôt

            # Calcul du résumé de la tournée
            total_distance_meters = 0
            if route_info.get('legs'): # Si on a les détails des legs
                 for leg in route_info['legs']:
                    total_distance_meters += leg['distance']['value']
            total_duration_seconds = 0
            if route_info.get('legs'):
                for leg in route_info['legs']:
                    total_duration_seconds += leg['duration_in_traffic']['value']
            
            total_duration_visit_seconds = sum((s['dur'] * 60) for s in simulated_stops if s['type'] != 'Dépôt')
            
            total_duration_simulated = (simulated_stops[-1]['departure_time'] - simulated_stops[0]['departure_time']).total_seconds() if len(simulated_stops) > 1 else 0

            total_distance_km = total_distance_meters / 1000
            total_duration_visit_h = total_duration_visit_seconds / 3600
            total_duration_driving_h = total_duration_seconds / 3600
            
            # Durée de la tournée simulée (du départ du dépôt à l'arrivée au dernier point)
            if simulated_stops and len(simulated_stops) > 1:
                tournee_start = simulated_stops[0]['departure_time']
                tournee_end = simulated_stops[-1]['departure_time'] # Ou arrivée si le dernier point est le dépôt
                if simulated_stops[-1]['type'] == 'Dépôt' and simulated_stops[-1]['arrival_time']:
                    tournee_end = simulated_stops[-1]['arrival_time']
                
                total_tournee_duration_h = (tournee_end - tournee_start).total_seconds() / 3600
            else:
                total_tournee_duration_h = 0


            st.subheader("Résumé de la Tournée")
            st.markdown(f"**Distance Totale :** {total_distance_km:.2f} km")
            st.markdown(f"**Temps de Conduite Estimé :** {total_duration_driving_h:.2f} h")
            st.markdown(f"**Temps Total sur les Visites :** {total_duration_visit_h:.2f} h")
            st.markdown(f"**Durée Totale de la Tournée (Estimée) :** {total_tournee_duration_h:.2f} h")

        else:
            st.warning("Impossible de générer la liste des arrêts.")

        # Bouton pour revenir à l'étape 1
        if st.button("Modifier la Tournée", key="modify_tour"):
            st.session_state.step = 1
            st.rerun()
            
        # Bouton pour exporter en PDF (à implémenter)
        # if st.button("Exporter en PDF", key="export_pdf"):
        #     st.info("Fonctionnalité d'export PDF bientôt disponible !")

    else:
        st.error("Un problème est survenu lors du calcul de l'itinéraire. Veuillez vérifier vos adresses et votre clé API.")
        if st.button("Retour à l'Étape 1", key="back_to_step1_error"):
            st.session_state.step = 1
            st.rerun()
