import streamlit as st
import googlemaps
from streamlit_folium import folium_static
import folium
from datetime import datetime, timedelta
import polyline
from collections import defaultdict
import logging

# Configuration du logging pour mieux suivre les étapes
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURATION & STYLE ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

# S'assurer que les clés API et le client Google Maps sont initialisés une seule fois
if 'gmaps' not in st.session_state:
    API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY", "VOTRE_CLE_API_GOOGLE_MAPS")
    if API_KEY == "VOTRE_CLE_API_GOOGLE_MAPS":
        st.error("Veuillez configurer votre clé API Google Maps dans les secrets Streamlit (`secrets.toml`).")
        st.stop()
    try:
        st.session_state.gmaps = googlemaps.Client(key=API_KEY)
        st.session_state.gmaps.geocode("Test") # Vérification basique de la clé API
        logging.info("Client Google Maps initialisé avec succès.")
    except Exception as e:
        st.error(f"Erreur lors de l'initialisation du client Google Maps. Vérifiez votre clé API. Détails : {e}")
        st.stop()

if 'map_style' not in st.session_state:
    st.session_state.map_style = """
    <style>
    .summary-box { padding: 6px 12px; border-radius: 8px; margin-bottom: 5px; display: flex; align-items: center; color: white; font-size: 0.9rem; }
    .depot-box { background-color: #28a745; border: 1px solid #1e7e34; }
    .client-box { background-color: #0047AB; border: 1px solid #003380; }
    .constraint-badge { background-color: #ffc107; color: #333; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px; }
    .forced-return-badge { background-color: #fd7e14; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px; }
    .depot-constraint-badge { background-color: #17a2b8; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px; }
    .arrival-time { font-weight: bold; margin-left: auto; }
    .departure-time { font-style: italic; margin-left: 10px; color: #ccc;}
    .time-on-site { font-size: 0.8rem; color: #aaa; margin-left: 10px;}
    [data-testid="stHorizontalBlock"] { align-items: center; }
    .client-card { background-color: #0047AB; color: white; padding: 10px; border-radius: 5px; margin-bottom: 5px; display: flex; justify-content: space-between; align-items: center;}
    .client-card-name { font-weight: bold; }
    .client-card-details { font-size: 0.85rem; }
    .client-card-constraints { font-size: 0.75rem; color: #ffc107; margin-left: 10px;}
    .stop-summary { font-size: 0.8rem; color: #aaa; }
    .folium-map { border-radius: 10px; }
    </style>
    """
    st.markdown(st.session_state.map_style, unsafe_allow_html=True)

# --- FONCTIONS UTILITAIRES ---

def get_coordinates(address):
    """Récupère les coordonnées (lat, lng) pour une adresse donnée."""
    try:
        geocode_result = st.session_state.gmaps.geocode(address)
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            logging.debug(f"Coordonnées trouvées pour '{address}': Lat={location['lat']}, Lng={location['lng']}")
            return location['lat'], location['lng']
        else:
            logging.warning(f"Adresse non trouvée pour le géocodage: {address}")
            return None, None
    except Exception as e:
        logging.error(f"Erreur de géocodage pour {address}: {e}")
        return None, None

def get_distance_and_duration(origin, destination):
    """Récupère la distance et la durée d'un trajet entre deux points."""
    try:
        now = datetime.now()
        directions_result = st.session_state.gmaps.directions(
            origin,
            destination,
            mode="driving",
            departure_time=now
        )
        if directions_result:
            leg = directions_result[0]['legs'][0]
            distance_meters = leg['distance']['value']
            duration_seconds = leg['duration']['value']
            # Utiliser la durée de trafic en temps réel si disponible
            if 'duration_in_traffic' in leg:
                duration_seconds = leg['duration_in_traffic']['value']

            logging.debug(f"Distance/Durée entre {origin} et {destination}: {distance_meters}m, {duration_seconds}s")
            return distance_meters, duration_seconds
        else:
            logging.warning(f"Aucune route trouvée entre {origin} et {destination}")
            return None, None
    except Exception as e:
        logging.error(f"Erreur API Google Maps pour distance/durée {origin} -> {destination}: {e}")
        return None, None

def calculate_route_times(stops_data, start_time, time_on_site_default, max_wait_time_default):
    """Calcule les temps d'arrivée et de départ pour chaque arrêt, sans contraintes complexes."""
    route = []
    current_time = start_time
    total_duration = 0
    total_distance = 0

    logging.info(f"Calcul des temps de trajet: {len(stops_data)} arrêts, Heure de départ: {start_time.strftime('%H:%M')}")

    for i, stop in enumerate(stops_data):
        stop_info = stop.copy() # Copier pour éviter de modifier l'original directement ici

        # Obtenir les coordonnées si pas déjà présentes
        if 'lat' not in stop_info or 'lng' not in stop_info or stop_info['lat'] is None or stop_info['lng'] is None:
            stop_info['lat'], stop_info['lng'] = get_coordinates(stop_info['address'])
            if stop_info['lat'] is None:
                logging.error(f"Impossible de géocoder l'arrêt {i+1}: {stop_info['address']}. Arrêt de l'optimisation.")
                return [], 0, 0 # Retourner vide si une coordonnée manque

        # Premier arrêt (dépôt)
        if i == 0:
            stop_info['arrival_time'] = current_time
            stop_info['departure_time'] = current_time
            stop_info['time_on_site'] = timedelta(minutes=0)
            route.append(stop_info)
            logging.debug(f"Arrêt Dépôt (0): Arrivée={stop_info['arrival_time'].strftime('%H:%M')}, Départ={stop_info['departure_time'].strftime('%H:%M')}")
            continue

        # Pour les autres arrêts
        previous_stop = route[-1]
        origin_coords = f"{previous_stop['lat']},{previous_stop['lng']}"
        destination_coords = f"{stop_info['lat']},{stop_info['lng']}"

        distance, duration = get_distance_and_duration(origin_coords, destination_coords)

        if distance is None or duration is None:
            logging.error(f"Échec du calcul distance/durée pour l'arrêt {i+1}. Arrêt.")
            return [], 0, 0

        total_distance += distance
        travel_duration = timedelta(seconds=duration)
        total_duration += duration

        # Calcul de l'heure d'arrivée
        current_time += travel_duration
        stop_info['arrival_time'] = current_time

        # Calcul de l'heure de départ (incluant le temps sur place)
        time_on_site = timedelta(minutes=stop_info.get('time_on_site', time_on_site_default))
        stop_info['time_on_site'] = time_on_site
        current_time += time_on_site
        stop_info['departure_time'] = current_time

        route.append(stop_info)
        logging.debug(f"Arrêt {i} ({stop['type']}): Arrivée={stop_info['arrival_time'].strftime('%H:%M')}, Départ={stop_info['departure_time'].strftime('%H:%M')}, Temps sur site={time_on_site}")

    logging.info(f"Calcul terminé. Durée totale trajet: {timedelta(seconds=total_duration)}, Distance totale: {total_distance}m.")
    return route, total_distance, total_duration


def calculate_route_with_constraints(stops_data, start_time, time_on_site_default, max_wait_time_default, forcing_return_aller_stops):
    """
    Calcule les temps et l'ordre des arrêts en tenant compte des contraintes horaires
    et de la logique "Ramasse Aller".
    """
    final_route = []
    current_time = start_time
    total_duration = 0
    total_distance = 0

    # Dépôt de départ
    depot = stops_data[0]
    depot['arrival_time'] = current_time
    depot['departure_time'] = current_time
    depot['time_on_site'] = timedelta(minutes=0)
    final_route.append(depot)
    logging.info(f"Calcul avec contraintes: Départ Dépôt {depot['address']} à {current_time.strftime('%H:%M')}")

    # Séparer les arrêts en Livraisons, Ramasses, et Ramasses Forcés à l'aller
    deliveries = [s for s in stops_data[1:] if s['type'] == 'Livraison']
    pickups = [s for s in stops_data[1:] if s['type'] == 'Ramasse' and s['id'] not in forcing_return_aller_stops]
    forced_pickups_aller = [s for s in stops_data[1:] if s['type'] == 'Ramasse' and s['id'] in forcing_return_aller_stops]

    # Logique Chauffeur: D'abord les livraisons, puis les ramasses
    # Ajouter les ramasses forcés à l'aller DANS la liste des livraisons pour l'ordre
    ordered_stops = deliveries + forced_pickups_aller + pickups

    # Assurer les coordonnées pour tous les arrêts avant le calcul principal
    for i, stop in enumerate(ordered_stops):
         if 'lat' not in stop or 'lng' not in stop or stop['lat'] is None or stop['lng'] is None:
            stop['lat'], stop['lng'] = get_coordinates(stop['address'])
            if stop['lat'] is None:
                logging.error(f"Impossible de géocoder l'arrêt {i+1} (type: {stop['type']}): {stop['address']}. Arrêt.")
                return [], 0, 0

    current_location_coords = f"{depot['lat']},{depot['lng']}" # Coordonnées du dépôt

    # Boucle principale de calcul
    stops_to_process = ordered_stops[:] # Copie pour pouvoir modifier et retirer des éléments
    
    while stops_to_process:
        best_stop_index = -1
        min_arrival_time = datetime.max
        
        candidate_stops = []
        
        # Considérer les arrêts qui peuvent être traités maintenant
        for i, stop in enumerate(stops_to_process):
            stop_address_for_gmaps = f"{stop['lat']},{stop['lng']}"
            
            # Calculer le temps de trajet potentiel
            distance, duration = get_distance_and_duration(current_location_coords, stop_address_for_gmaps)
            if distance is None or duration is None:
                logging.warning(f"Impossible de calculer trajet vers {stop['address']}. Sera sauté pour cette itération.")
                continue # Essayer le suivant

            travel_duration = timedelta(seconds=duration)
            potential_arrival_time = current_time + travel_duration
            
            # Vérifier contrainte horaire
            arrival_time_adjusted = potential_arrival_time
            wait_time = timedelta(minutes=0)
            
            is_delivery = stop['type'] == 'Livraison'
            is_forced_pickup_aller = stop['type'] == 'Ramasse' and stop['id'] in forcing_return_aller_stops
            
            # On applique la contrainte horaire seulement aux livraisons ou ramasses forcés à l'aller
            if stop.get('horaire_imperatif') and (is_delivery or is_forced_pickup_aller):
                try:
                    earliest_time, latest_time = stop['horaire_debut'], stop['horaire_fin']
                    
                    # Si on arrive trop tôt, on doit attendre
                    if potential_arrival_time < earliest_time:
                        wait_time = earliest_time - potential_arrival_time
                        # Si l'attente est trop longue, on marque un problème (mais on continue pour l'instant)
                        if wait_time > timedelta(minutes=max_wait_time_default):
                           logging.warning(f"Attente potentiellement trop longue ({wait_time}) à {stop['address']} ({stop['horaire_debut'].strftime('%H:%M')}). L'itinéraire sera quand même calculé.")
                           # On ne va pas réorganiser ici, mais on prévient. L'arrivée sera ajustée.
                        arrival_time_adjusted = earliest_time
                    # Si on arrive après la fin, c'est un problème (on ne peut pas rattraper)
                    elif potential_arrival_time > latest_time:
                        # On ne peut pas honorer la contrainte. On marque et on continue.
                        stop['constraint_violated'] = True
                        arrival_time_adjusted = potential_arrival_time # On arrive quand même, même en retard
                        logging.warning(f"Arrivée potentielle ({potential_arrival_time.strftime('%H:%M')}) en retard à {stop['address']} (fenêtre: {earliest_time.strftime('%H:%M')}-{latest_time.strftime('%H:%M')}).")

                except (ValueError, TypeError) as e:
                     logging.warning(f"Erreur de parsing horaire pour {stop['address']}: {e}. Ignoré.")
                     stop['constraint_violated'] = False # Pas de contrainte forcée si mal parsé


            # Stocker ce candidat pour trouver le plus proche/rapide
            candidate_stops.append({
                'index': i,
                'stop': stop,
                'arrival_time': arrival_time_adjusted,
                'travel_duration': travel_duration,
                'distance': distance,
                'wait_time': wait_time
            })

        # Trouver le meilleur prochain arrêt parmi les candidats
        if not candidate_stops:
            logging.error("Aucun arrêt accessible trouvé. Arrêt de l'optimisation.")
            break # Sortir de la boucle si aucun arrêt n'est atteignable

        # Choisir le candidat qui arrive le plus tôt (en tenant compte de l'attente)
        candidate_stops.sort(key=lambda x: x['arrival_time'])
        best_candidate = candidate_stops[0]
        
        best_stop_index = best_candidate['index']
        chosen_stop = best_candidate['stop']
        
        # Mettre à jour le temps courant
        current_time = best_candidate['arrival_time']
        
        # Mettre à jour les informations de l'arrêt choisi
        chosen_stop['arrival_time'] = best_candidate['arrival_time']
        chosen_stop['travel_duration'] = best_candidate['travel_duration']
        chosen_stop['distance_from_previous'] = best_candidate['distance']
        chosen_stop['wait_time'] = best_candidate['wait_time']
        
        time_on_site = timedelta(minutes=chosen_stop.get('time_on_site', time_on_site_default))
        chosen_stop['time_on_site'] = time_on_site
        
        chosen_stop['departure_time'] = current_time + time_on_site
        
        # Mise à jour des totaux
        total_distance += chosen_stop['distance_from_previous']
        total_duration += chosen_stop['travel_duration'].total_seconds() + chosen_stop['time_on_site'].total_seconds()

        # Ajouter l'arrêt à la route finale
        final_route.append(chosen_stop)
        
        # Mettre à jour la position actuelle pour le prochain calcul
        current_location_coords = f"{chosen_stop['lat']},{chosen_stop['lng']}"
        current_time = chosen_stop['departure_time'] # Le départ de cet arrêt est l'heure de départ pour le suivant

        # Retirer l'arrêt traité de la liste des arrêts à traiter
        stops_to_process.pop(best_stop_index)
        
        logging.debug(f"Prochain arrêt choisi: {chosen_stop['address']} ({chosen_stop['type']}). Arrivée: {chosen_stop['arrival_time'].strftime('%H:%M')}, Départ: {chosen_stop['departure_time'].strftime('%H:%M')}. Attente: {chosen_stop['wait_time']}. Temps sur site: {chosen_stop['time_on_site']}")

    # Ajouter le retour au dépôt final si nécessaire (par exemple, si le dernier arrêt n'est pas le dépôt)
    if final_route and final_route[-1]['id'] != depot['id']:
         last_stop = final_route[-1]
         depot_return_coords = f"{depot['lat']},{depot['lng']}"
         last_stop_coords = f"{last_stop['lat']},{last_stop['lng']}"
         
         distance, duration = get_distance_and_duration(last_stop_coords, depot_return_coords)
         if distance is not None and duration is not None:
             travel_duration = timedelta(seconds=duration)
             depot_arrival_time = current_time + travel_duration
             
             depot_return_data = depot.copy()
             depot_return_data['address'] = f"Retour Dépôt ({depot['address']})"
             depot_return_data['type'] = 'Retour Dépôt'
             depot_return_data['arrival_time'] = depot_arrival_time
             depot_return_data['departure_time'] = depot_arrival_time # Pas de temps sur site pour le retour
             depot_return_data['time_on_site'] = timedelta(minutes=0)
             depot_return_data['distance_from_previous'] = distance
             depot_return_data['travel_duration'] = travel_duration
             
             final_route.append(depot_return_data)
             total_distance += distance
             total_duration += duration
             logging.info(f"Retour au dépôt ajouté. Arrivée prévue: {depot_arrival_time.strftime('%H:%M')}")
         else:
             logging.warning("Impossible de calculer le trajet de retour au dépôt.")

    logging.info(f"Calcul avec contraintes terminé. Durée totale: {timedelta(seconds=total_duration)}, Distance totale: {total_distance}m.")
    return final_route, total_distance, total_duration


def plot_route_on_map(route, m):
    """Ajoute les étapes de la route sur la carte Folium."""
    if not route:
        return

    latlng_list = []
    for i, stop in enumerate(route):
        lat, lng = stop['lat'], stop['lng']
        if lat is None or lng is None: continue

        latlng_list.append((lat, lng))

        # Créer le popup personnalisé
        popup_html = f"""
        <div class='client-card'>
            <div style='display: flex; flex-direction: column;'>
                <span class='client-card-name'>{stop.get('name', f'Arrêt {i+1}')}</span>
                <span class='client-card-details'>{stop['address']}</span>
            </div>
        </div>
        <div style='padding: 5px;'>
            <span class='stop-summary'><strong>Type:</strong> {stop['type']}</span><br>
            <span class='stop-summary'><strong>Temps sur site:</strong> {stop.get('time_on_site', 'N/A')}</span><br>
            <span class='stop-summary'><strong>Arrivée:</strong> <span class='arrival-time'>{stop.get('arrival_time', 'N/A').strftime('%H:%M:%S') if isinstance(stop.get('arrival_time'), datetime) else 'N/A'}</span></span><br>
            <span class='stop-summary'><strong>Départ:</strong> <span class='departure-time'>{stop.get('departure_time', 'N/A').strftime('%H:%M:%S') if isinstance(stop.get('departure_time'), datetime) else 'N/A'}</span></span>
            """
        # Ajouter les contraintes spécifiques au popup
        if stop.get('horaire_imperatif'):
            popup_html += f"<span class='client-card-constraints'>Horaires: {stop['horaire_debut'].strftime('%H:%M')}-{stop['horaire_fin'].strftime('%H:%M')}</span><br>"
        if stop.get('forced_return_aller'):
             popup_html += f"<span class='client-card-constraints' style='background-color: #fd7e14;'>Ramasse Aller</span><br>"
        if stop.get('constraint_violated'):
            popup_html += f"<span class='client-card-constraints' style='background-color: red;'>Contrainte Horaire Non Respectée</span><br>"
        if 'distance_from_previous' in stop and stop['distance_from_previous'] is not None:
             popup_html += f"<span class='stop-summary'><strong>Distance depuis précédent:</strong> {stop['distance_from_previous'] / 1000:.2f} km</span><br>"
             popup_html += f"<span class='stop-summary'><strong>Durée trajet:</strong> {stop.get('travel_duration', 'N/A')}</span><br>"

        popup_html += "</div>"

        # Icônes personnalisées
        icon_color = 'green'
        if stop['type'] == 'Livraison':
            icon_color = 'blue'
        elif stop['type'] == 'Ramasse':
            icon_color = 'orange'
        elif stop['type'] == 'Dépôt':
            icon_color = 'darkgreen'
        elif stop['type'] == 'Retour Dépôt':
            icon_color = 'gray'

        # Style de l'icône
        icon = folium.Icon(color=icon_color, icon='info-sign') # Vous pouvez changer 'info-sign' par 'truck', 'home', etc. si vous préférez

        # Ajouter le marqueur à la carte
        folium.Marker(
            location=[lat, lng],
            popup=folium.Popup(popup_html, max_width=300),
            icon=icon,
            tooltip=f"{stop['type']}: {stop.get('name', stop['address'])}"
        ).add_to(m)

    # Dessiner le polyline
    if len(latlng_list) > 1:
        try:
            # Utiliser l'API Google Maps pour obtenir le polyline encodé si possible
            origin_coords = f"{route[0]['lat']},{route[0]['lng']}"
            destination_coords = f"{route[-1]['lat']},{route[-1]['lng']}"
            
            # Obtenir les waypoints
            waypoints = []
            if len(route) > 2:
                 waypoints = [(f"{stop['lat']},{stop['lng']}") for stop in route[1:-1]]

            directions_result = st.session_state.gmaps.directions(
                origin_coords,
                destination_coords,
                mode="driving",
                waypoints=waypoints if waypoints else None,
                optimize_waypoints=False # Important: nous avons déjà notre ordre
            )

            if directions_result and directions_result[0].get('overview_polyline'):
                encoded_polyline = directions_result[0]['overview_polyline']['points']
                decoded_points = polyline.decode(encoded_polyline)
                folium.PolyLine(
                    locations=decoded_points,
                    color='blue',
                    weight=5,
                    opacity=0.7,
                    tooltip="Itinéraire"
                ).add_to(m)
            else:
                 # Fallback: dessiner une ligne simple entre les points si l'API ne renvoie pas de polyline
                 folium.PolyLine(
                    locations=latlng_list,
                    color='red',
                    weight=3,
                    opacity=0.5,
                    tooltip="Itinéraire (simplifié)"
                 ).add_to(m)
        except Exception as e:
            logging.error(f"Erreur lors du dessin du polyline: {e}. Dessin simplifié.")
            folium.PolyLine(
                locations=latlng_list,
                color='red',
                weight=3,
                opacity=0.5,
                tooltip="Itinéraire (simplifié)"
             ).add_to(m)


# --- INTERFACE UTILISATEUR STREAMLIT ---

st.title("🚚 Planificateur de Tournées Suisse")
st.markdown("Optimisez vos livraisons et ramasses en Suisse avec une planification intelligente.")

# --- Configuration de la Session ---
if 'stops' not in st.session_state:
    st.session_state.stops = []
if 'start_time' not in st.session_state:
    st.session_state.start_time = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
if 'time_on_site_default' not in st.session_state:
    st.session_state.time_on_site_default = 15 # Minutes
if 'max_wait_time_default' not in st.session_state:
    st.session_state.max_wait_time_default = 30 # Minutes
if 'forcing_return_aller_stops' not in st.session_state:
    st.session_state.forcing_return_aller_stops = set() # IDs des arrêts à forcer à l'aller

# --- Colonnes pour la mise en page ---
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Paramètres de la Tournée")

    # Dépôt
    st.text_input("Adresse du Dépôt", value="Crissier, Route de Lausanne 11, 1030 Crissier", key="depot_address")
    depot_lat, depot_lng = get_coordinates(st.session_state.depot_address)
    if depot_lat and depot_lng:
        st.session_state.stops = [{'id': 0, 'address': st.session_state.depot_address, 'type': 'Dépôt', 'lat': depot_lat, 'lng': depot_lng, 'name': 'Dépôt'}] + st.session_state.stops[1:]
    else:
        st.warning("Veuillez entrer une adresse de dépôt valide.")


    # Heure de début
    time_input = st.time_input("Heure de début de la tournée", value=st.session_state.start_time.time(), key="start_time_input")
    if time_input != st.session_state.start_time.time():
        st.session_state.start_time = datetime.combine(datetime.today(), time_input) # Combinaison avec date du jour

    # Temps sur site par défaut
    st.number_input("Temps moyen sur site (min)", min_value=1, max_value=60, value=st.session_state.time_on_site_default, key="time_on_site_default")

    # Délai d'attente maximum
    st.number_input("Délai d'attente max avant réorganisation (min)", min_value=5, max_value=120, value=st.session_state.max_wait_time_default, key="max_wait_time_default")


    st.subheader("Ajouter un Arrêt")
    with st.form(key='stop_form'):
        address = st.text_input("Adresse de l'arrêt", placeholder="ex: Grand-Rue 1, 1110 Morges")
        stop_type = st.selectbox("Type d'arrêt", ["Livraison", "Ramasse"], key="stop_type_select")
        name = st.text_input("Nom du client/lieu (optionnel)", key="stop_name")
        time_on_site_specific = st.number_input("Temps sur site spécifique (min, laisser vide pour défaut)", key="stop_time_on_site", value=None, format="%d")
        
        # Contraintes
        horaire_imperatif = st.checkbox("Contrainte Horaire Impérative", key="horaire_imperatif_checkbox")
        horaire_debut_str, horaire_fin_str = "", ""
        if horaire_imperatif:
            col_h1, col_h2 = st.columns(2)
            with col_h1:
                 horaire_debut_str = st.text_input("Heure début (HH:MM)", placeholder="09:00", key="horaire_debut_input")
            with col_h2:
                 horaire_fin_str = st.text_input("Heure fin (HH:MM)", placeholder="17:00", key="horaire_fin_input")

        force_return_aller = st.checkbox("Forcer ce Ramasse à l'aller", key="force_return_aller_checkbox")

        submit_button = st.form_submit_button("Ajouter l'Arrêt")

        if submit_button and address:
            try:
                stop_id_counter = max(s.get('id', 0) for s in st.session_state.stops) + 1
                new_stop = {
                    'id': stop_id_counter,
                    'address': address,
                    'type': stop_type,
                    'name': name if name else f"{stop_type} {stop_id_counter}",
                    'time_on_site': time_on_site_specific,
                    'horaire_imperatif': horaire_imperatif,
                    'horaire_debut': None,
                    'horaire_fin': None,
                    'forced_return_aller': force_return_aller,
                    'constraint_violated': False # Initialisation
                }

                # Parsing des heures si contrainte horaire cochée
                if horaire_imperatif:
                    try:
                        # Utiliser la date d'aujourd'hui pour pouvoir comparer les heures
                        today_date = datetime.today().date()
                        new_stop['horaire_debut'] = datetime.combine(today_date, datetime.strptime(horaire_debut_str, "%H:%M").time())
                        new_stop['horaire_fin'] = datetime.combine(today_date, datetime.strptime(horaire_fin_str, "%H:%M").time())
                        # Assurer que debut <= fin
                        if new_stop['horaire_debut'] > new_stop['horaire_fin']:
                             st.warning("L'heure de début de la contrainte horaire est postérieure à l'heure de fin. Inversion pour le calcul.")
                             new_stop['horaire_debut'], new_stop['horaire_fin'] = new_stop['horaire_fin'], new_stop['horaire_debut']
                    except ValueError:
                        st.warning(f"Format d'heure invalide pour '{horaire_debut_str}' ou '{horaire_fin_str}'. La contrainte horaire sera ignorée.")
                        new_stop['horaire_imperatif'] = False

                # Si c'est un ramasse forcé à l'aller, ajouter son ID à la liste de session
                if force_return_aller:
                    st.session_state.forcing_return_aller_stops.add(stop_id_counter)
                    logging.info(f"Ramasse ID {stop_id_counter} ({address}) marqué pour être forcé à l'aller.")

                # Ajout à la liste des arrêts
                st.session_state.stops.append(new_stop)
                st.success("Arrêt ajouté avec succès !")
                st.experimental_rerun() # Rafraîchir pour voir le nouvel arrêt

            except Exception as e:
                st.error(f"Erreur lors de l'ajout de l'arrêt: {e}")

    st.subheader("Itinéraire Actuel")
    if not st.session_state.stops or len(st.session_state.stops) < 2:
        st.info("Ajoutez le Dépôt et au moins un arrêt pour générer un itinéraire.")
    else:
        # Préparation des données pour le calcul
        # S'assurer que le dépôt est toujours le premier élément
        depot_data = next((s for s in st.session_state.stops if s['type'] == 'Dépôt'), None)
        other_stops = [s for s in st.session_state.stops if s['type'] != 'Dépôt']
        
        # Assurer la présence des IDs pour le set forcing_return_aller_stops
        for s in other_stops:
            if 'id' not in s: s['id'] = max(st.session_state.stops, key=lambda x: x.get('id', 0))['id'] + 1

        ordered_stops_for_calculation = [depot_data] + other_stops if depot_data else other_stops

        # Recalculer le temps sur site si besoin
        for stop in ordered_stops_for_calculation:
             if stop.get('time_on_site') is None:
                 stop['time_on_site'] = st.session_state.time_on_site_default
             else: # Assurer que c'est bien un int/float si l'utilisateur l'a saisi
                 stop['time_on_site'] = int(stop['time_on_site'])

        # Calculer l'itinéraire
        # Utilisation de la fonction avec contraintes
        calculated_route, total_distance_km, total_duration_sec = calculate_route_with_constraints(
            ordered_stops_for_calculation,
            st.session_state.start_time,
            st.session_state.time_on_site_default,
            st.session_state.max_wait_time_default,
            st.session_state.forcing_return_aller_stops
        )

        # Affichage de la feuille de route
        st.write("---")
        st.subheader("Feuille de Route Détaillée")
        if not calculated_route:
            st.warning("Aucune route calculée. Vérifiez les erreurs.")
        else:
            route_summary_html = ""
            for i, stop in enumerate(calculated_route):
                is_last = (i == len(calculated_route) - 1)
                
                # Déterminer la classe CSS en fonction du type d'arrêt
                box_class = "summary-box depot-box" if stop['type'] == 'Dépôt' else "summary-box client-box"
                if stop['type'] == 'Retour Dépôt':
                    box_class = "summary-box depot-constraint-badge" # Style différent pour retour

                # Formatage des temps
                arrival_str = stop.get('arrival_time').strftime('%H:%M:%S') if isinstance(stop.get('arrival_time'), datetime) else "N/A"
                departure_str = stop.get('departure_time').strftime('%H:%M:%S') if isinstance(stop.get('departure_time'), datetime) else "N/A"
                time_on_site_str = str(stop.get('time_on_site', 'N/A'))

                # Icônes pour les contraintes
                constraint_icons = ""
                if stop.get('horaire_imperatif'):
                    constraint_icons += "<span class='constraint-badge'>Horaires</span>"
                if stop.get('forced_return_aller'):
                     constraint_icons += "<span class='forced-return-badge'>Ramasse Aller</span>"
                if stop.get('constraint_violated'):
                    constraint_icons += "<span class='constraint-badge' style='background-color: red;'>Retard</span>"
                
                # Calcul des durées de trajet et attente pour affichage
                travel_duration_display = str(stop.get('travel_duration', 'N/A'))
                wait_time_display = str(stop.get('wait_time', 'N/A')) if stop.get('wait_time', timedelta(0)).total_seconds() > 0 else ""

                # Affichage de la ligne d'arrêt
                route_summary_html += f"""
                <div class='{box_class}'>
                    <strong>{i+1}. {stop.get('name', stop['address'])}</strong> ({stop['type']})
                    <span class='arrival-time'>Arr: {arrival_str}</span>
                    <span class='departure-time'>Dep: {departure_str}</span>
                    <span class='time-on-site'>[{time_on_site_str} min]</span>
                    {constraint_icons}
                </div>
                """
                if travel_duration_display != 'N/A':
                    route_summary_html += f"<div class='stop-summary' style='margin-left: 25px;'> Trajet: {travel_duration_display} {f' | Attente: {wait_time_display}' if wait_time_display else ''}</div>"
                
                # Marqueur pour la fin de la tournée
                if is_last and stop['type'] != 'Retour Dépôt':
                    route_summary_html += "<div class='summary-box client-box'><strong>Fin de Tournée</strong></div>"


            st.markdown(route_summary_html, unsafe_allow_html=True)

            # Affichage du résumé
            st.subheader("Résumé de la Tournée")
            total_distance_km_val = total_distance_km / 1000 if total_distance_km else 0
            total_duration_formatted = str(timedelta(seconds=total_duration_sec))
            st.markdown(f"**Distance Totale :** `{total_distance_km_val:.2f} km`")
            st.markdown(f"**Durée Estimée (Trajets + Temps sur site) :** `{total_duration_formatted}`")


with col2:
    st.subheader("Carte de la Tournée")
    if not calculated_route or not any(stop.get('lat') and stop.get('lng') for stop in calculated_route):
        st.info("Veuillez ajouter des arrêts et calculer l'itinéraire pour visualiser la carte.")
        # Créer une carte vide si rien n'est calculé
        m = folium.Map(location=[46.52, 6.63], zoom_start=10, tiles="OpenStreetMap", zoom_control=True, scrollWheelZoom=False)
    else:
        # Centrer la carte sur le premier arrêt (dépôt) ou sur la moyenne des points
        center_lat = calculated_route[0]['lat'] if calculated_route else 46.52
        center_lng = calculated_route[0]['lng'] if calculated_route else 6.63
        
        # Trouver les limites de la carte pour un zoom optimal
        all_lats = [stop['lat'] for stop in calculated_route if stop.get('lat')]
        all_lngs = [stop['lng'] for stop in calculated_route if stop.get('lng')]
        
        if all_lats and all_lngs:
             center_lat = sum(all_lats) / len(all_lats)
             center_lng = sum(all_lngs) / len(all_lngs)
             
        m = folium.Map(location=[center_lat, center_lng], zoom_start=10, tiles="CartoDB positron", zoom_control=True, scrollWheelZoom=True)

        # Dessiner la route sur la carte
        plot_route_on_map(calculated_route, m)

    # Afficher la carte Folium dans Streamlit
    folium_static(m, height=600)


# --- Bouton pour supprimer les arrêts ---
st.markdown("---")
st.subheader("Gestion des Arrêts")
if len(st.session_state.stops) > 1: # Permet de garder le dépôt
    # Afficher la liste des arrêts avec des boutons de suppression
    stop_ids_to_remove = []
    cols = st.columns([1, 8, 1]) # Colonne pour case à cocher, adresse, bouton supprimer
    
    # On commence à l'index 1 pour ne pas supprimer le dépôt
    for i, stop in enumerate(st.session_state.stops[1:]):
        with cols[0]:
            # Créer un key unique pour chaque checkbox basée sur l'id de l'arrêt
            if st.checkbox("", key=f"remove_stop_{stop['id']}"):
                stop_ids_to_remove.append(stop['id'])
        with cols[1]:
            st.markdown(f"**{stop['name']}** ({stop['address']}) - {stop['type']}")
        with cols[2]:
            # Créer un key unique pour chaque bouton supprimer basé sur l'id de l'arrêt
            if st.button("Supprimer", key=f"delete_btn_{stop['id']}"):
                stop_ids_to_remove.append(stop['id'])

    if st.button("Supprimer les arrêts sélectionnés"):
        original_stops = st.session_state.stops[1:] # Exclure le dépôt
        # Filtrer pour garder seulement les arrêts dont l'ID n'est PAS dans stop_ids_to_remove
        st.session_state.stops = [st.session_state.stops[0]] + [s for s in original_stops if s['id'] not in stop_ids_to_remove]
        
        # Aussi, retirer des ramasses forcés si supprimés
        st.session_state.forcing_return_aller_stops = {
            stop_id for stop_id in st.session_state.forcing_return_aller_stops
            if stop_id not in stop_ids_to_remove
        }
        
        st.success("Arrêts supprimés. Veuillez recalculer l'itinéraire.")
        st.experimental_rerun() # Rafraîchir pour voir la liste mise à jour

else:
    st.info("Aucun arrêt à supprimer pour le moment (à part le dépôt).")

# --- Affichage des secrets (pour débogage si nécessaire) ---
# with st.expander("Voir les secrets (pour débogage)"):
#     st.json(st.secrets.to_dict())
