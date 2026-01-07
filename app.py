import streamlit as st
import googlemaps
import folium
from folium.plugins import PolyLine
from streamlit_folium import folium_static
from datetime import datetime, timedelta
import polyline as polyline_lib # Renommé pour éviter conflit si 'polyline' est utilisé ailleurs
import os

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Planificateur de Tournée Professionnelle",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- TITRE DE L'APPLICATION ---
st.title("🚗 Planificateur de Tournée Professionnelle")

# --- INITIALISATION DE LA SESSION STATE ---
if 'stops' not in st.session_state:
    st.session_state.stops = []
if 'depot' not in st.session_state:
    st.session_state.depot = None
if 'mode_optimisation' not in st.session_state:
    st.session_state.mode_optimisation = "Livraisons avant Ramasses" # Valeur par défaut

# --- CONNEXION À L'API GOOGLE MAPS ---
# Assurez-vous que votre clé API est correctement configurée dans Streamlit Secrets
# Exemple pour config.toml :
# [google]
# api_key = "VOTRE_CLE_API_GOOGLE_MAPS"

try:
    # Tentative de récupérer la clé API de st.secrets
    api_key = st.secrets["google"]["api_key"]
    gmaps = googlemaps.Client(key=api_key)
except KeyError:
    st.error("Erreur : La clé API Google Maps n'est pas configurée. Veuillez la définir dans vos secrets Streamlit.")
    st.stop() # Arrête l'exécution si la clé n'est pas trouvée

# --- FONCTIONS UTILITAIRES ---

def get_coordinates(address, geolocator):
    """Récupère les coordonnées (latitude, longitude) d'une adresse."""
    try:
        location = geolocator.geocode(address)
        if location:
            return (location.latitude, location.longitude)
        else:
            st.warning(f"Impossible de géocoder l'adresse : {address}")
            return None
    except Exception as e:
        st.error(f"Erreur lors du géocodage de {address} : {e}")
        return None

def calculate_route(locations_coords, waypoints=None, optimize_waypoints=True):
    """Calcule une route entre plusieurs points en utilisant l'API Google Maps."""
    if not locations_coords:
        return None, None

    origin = locations_coords[0]
    destination = locations_coords[-1]
    
    # Les waypoints sont les points intermédiaires (tous sauf origin et destination)
    # Si waypoints est fourni, on l'utilise directement. Sinon, on le déduit.
    if waypoints is None:
        waypoints = locations_coords[1:-1] if len(locations_coords) > 2 else []

    try:
        # L'optimisation des waypoints est importante pour trouver le meilleur ordre
        directions_result = gmaps.directions(
            origin,
            destination,
            waypoints=waypoints,
            mode="driving",
            optimize_waypoints=optimize_waypoints,
            departure_time=datetime.now() # Utilise l'heure actuelle pour estimer le trafic
        )

        if not directions_result:
            st.error("Aucun itinéraire trouvé par l'API Google Maps.")
            return None, None

        route = directions_result[0]
        distance = route['legs'][0]['distance']['text']
        duration = route['legs'][0]['duration']['text']
        encoded_polyline = route['overview_polyline']['points']
        
        # Récupérer l'ordre des waypoints optimisés s'il y a lieu
        waypoint_order = route.get('waypoint_order', [])
        
        return route, waypoint_order
        
    except googlemaps.exceptions.ApiError as e:
        st.error(f"Erreur de l'API Google Maps : {e}")
        return None, None
    except Exception as e:
        st.error(f"Erreur inattendue lors du calcul de l'itinéraire : {e}")
        return None, None

def get_route_details_for_stops(ordered_stops, gmaps_client):
    """Calcule les détails (distance, durée) entre chaque arrêt consécutif."""
    if len(ordered_stops) < 2:
        return []

    detailed_routes = []
    now = datetime.now() # Heure de départ

    # Calculer l'itinéraire du dépôt au premier arrêt
    depot_coords = get_coordinates(ordered_stops[0]['address'], gmaps_client)
    if not depot_coords: return [] # Si le dépôt n'a pas de coords, on arrête

    for i in range(len(ordered_stops) - 1):
        start_stop = ordered_stops[i]
        end_stop = ordered_stops[i+1]

        start_coords = get_coordinates(start_stop['address'], gmaps_client)
        end_coords = get_coordinates(end_stop['address'], gmaps_client)

        if not start_coords or not end_coords:
            continue # Passe au prochain segment si une coordonnée manque

        # Utiliser le point de départ correct : soit le dépôt, soit l'arrêt précédent
        if i == 0:
            current_origin = depot_coords
        else:
            current_origin = start_coords
        
        # On peut passer les points intermédiaires si on a une longue chaîne,
        # mais pour des tournées courtes, c'est souvent plus simple comme ça.
        # Ici, on ne calcule que le segment direct entre deux points.
        try:
            directions_result = gmaps_client.directions(
                current_origin,
                end_coords,
                mode="driving",
                departure_time=now, # L'heure de départ du segment
                optimize_waypoints=False # Pas besoin d'optimiser entre deux points connus
            )

            if directions_result:
                leg = directions_result[0]['legs'][0]
                distance_text = leg['distance']['text']
                duration_text = leg['duration']['text']
                encoded_polyline = directions_result[0]['overview_polyline']['points']
                
                detailed_routes.append({
                    "start_address": start_stop['address'],
                    "end_address": end_stop['address'],
                    "distance": distance_text,
                    "duration": duration_text,
                    "polyline": encoded_polyline
                })
                
                # Mettre à jour l'heure de départ pour le prochain segment
                # On ajoute la durée du segment actuel (convertie en secondes) plus un peu de marge
                duration_seconds = leg['duration']['value']
                now += timedelta(seconds=duration_seconds + 60) # Ajoute 60 secondes de marge

            else:
                st.warning(f"Aucun itinéraire trouvé entre {start_stop['address']} et {end_stop['address']}.")
        
        except googlemaps.exceptions.ApiError as e:
            st.error(f"Erreur API Google Maps pour le segment {start_stop['address']} -> {end_stop['address']} : {e}")
        except Exception as e:
            st.error(f"Erreur inattendue pour le segment {start_stop['address']} -> {end_stop['address']} : {e}")

    return detailed_routes


# --- Widgets de l'Interface ---

st.sidebar.header("⚙️ Paramètres")

# 1. Mode d'Optimisation
st.sidebar.subheader("Mode d'Optimisation")
optimization_modes = {
    "Livraisons avant Ramasses": "delivery_then_pickup",
    "Priorité Horaire (Moins d'attente, puis Livraisons -> Ramasses)": "time_priority",
    "Optimisation par Google Maps (Dépôt -> Points -> Dépôt)": "gmaps_optimize_full_route"
}
selected_mode_label = st.sidebar.radio(
    "Choisissez comment optimiser la tournée :",
    list(optimization_modes.keys()),
    index=list(optimization_modes.values()).index(st.session_state.mode_optimisation) # Index basé sur la valeur sauvegardée
)
st.session_state.mode_optimisation = optimization_modes[selected_mode_label]


# 2. Définir le Dépôt
st.sidebar.subheader("Dépôt de départ")
depot_address = st.sidebar.text_input("Adresse du dépôt :", key="depot_address_input", value=st.session_state.depot['address'] if st.session_state.depot else "")
if st.sidebar.button("Valider le dépôt"):
    if depot_address:
        depot_coords = get_coordinates(depot_address, gmaps)
        if depot_coords:
            st.session_state.depot = {
                "address": depot_address,
                "latitude": depot_coords[0],
                "longitude": depot_coords[1],
                "type": "depot"
            }
            st.sidebar.success("Dépôt défini !")
        else:
            st.sidebar.error("Impossible de géocoder l'adresse du dépôt.")
    else:
        st.sidebar.warning("Veuillez entrer une adresse pour le dépôt.")

# 3. Ajouter des Arrêts (Livraisons ou Ramasses)
st.sidebar.subheader("Ajouter un arrêt")
address = st.sidebar.text_input("Adresse de l'arrêt :", key="address_input")
stop_type = st.sidebar.radio("Type d'arrêt :", ["Livraison", "Ramasse"], key="stop_type_radio")
client_constraints = st.sidebar.text_area("Contraintes client (fenêtre horaire, notes...) :", key="constraints_input")
force_pickup_on_departure = st.sidebar.checkbox("Forcer ce point à l'aller (comme une livraison) ?", key="force_pickup_checkbox")

# Gestion de la case "Forcer à l'aller" qui n'est pertinente que pour les ramasses
if stop_type == "Livraison":
    st.session_state.force_pickup_checkbox = False # Décoche automatiquement si c'est une livraison

if st.sidebar.button("Ajouter l'arrêt"):
    if address:
        coords = get_coordinates(address, gmaps)
        if coords:
            stop_data = {
                "address": address,
                "latitude": coords[0],
                "longitude": coords[1],
                "type": stop_type,
                "constraints": client_constraints,
                "force_on_departure": force_pickup_on_departure if stop_type == "Ramasse" else False # S'applique seulement aux ramasses
            }
            st.session_state.stops.append(stop_data)
            # Réinitialiser les champs pour le prochain ajout
            st.session_state.address_input = ""
            st.session_state.constraints_input = ""
            st.session_state.stop_type_radio = "Livraison" # Retour au défaut
            st.session_state.force_pickup_checkbox = False
            st.experimental_rerun() # Rafraîchir pour montrer le nouvel arrêt dans la liste
        else:
            st.sidebar.error("Impossible de géocoder l'adresse de l'arrêt.")
    else:
        st.sidebar.warning("Veuillez entrer une adresse pour l'arrêt.")

# --- Affichage des Arrêts Ajoutés ---
st.subheader("Liste des Arrêts Ajoutés")
if not st.session_state.stops and not st.session_state.depot:
    st.info("Ajoutez d'abord votre dépôt et vos arrêts via la barre latérale.")
elif not st.session_state.depot:
    st.warning("Veuillez définir un dépôt de départ.")
else:
    # Préparation de la liste complète des points pour l'optimisation
    all_points_for_optimization = [st.session_state.depot] + st.session_state.stops
    
    # Affichage sous forme de liste simple avec leurs détails
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    col1.markdown("**Adresse**")
    col2.markdown("**Type**")
    col3.markdown("**Contraintes**")
    col4.markdown("**Actions**")

    for i, stop in enumerate(st.session_state.stops):
        col1.write(stop['address'])
        
        display_type = stop['type']
        if stop['type'] == "Ramasse" and stop.get('force_on_departure'):
            display_type += " (Forcée à l'aller)"
        col2.write(display_type)
        
        col3.write(stop['constraints'])
        
        # Boutons pour supprimer ou déplacer un arrêt
        col4.write("---") # Séparateur visuel
        
        # Bouton supprimer
        if st.sidebar.button(f"Supprimer l'arrêt {i+1}", key=f"delete_{i}"):
             st.session_state.stops.pop(i)
             st.experimental_rerun()

        # Boutons pour déplacer (avec logique pour gérer les types)
        if i > 0: # Bouton monter
            if st.sidebar.button(f"Monter arrêt {i+1}", key=f"up_{i}"):
                st.session_state.stops[i], st.session_state.stops[i-1] = st.session_state.stops[i-1], st.session_state.stops[i]
                st.experimental_rerun()
        if i < len(st.session_state.stops) - 1: # Bouton descendre
            if st.sidebar.button(f"Descendre arrêt {i+1}", key=f"down_{i}"):
                st.session_state.stops[i], st.session_state.stops[i+1] = st.session_state.stops[i+1], st.session_state.stops[i]
                st.experimental_rerun()
    
    # Bouton pour effacer tous les arrêts
    if st.button("Effacer tous les arrêts"):
        st.session_state.stops = []
        st.experimental_rerun()

    # --- ÉTAPE 2 : OPTIMISATION DE LA TOURNEE ---
    st.header("Étape 2 : Optimiser la Tournée")

    if st.button("Calculer la tournée optimale"):
        if not st.session_state.depot:
            st.error("Veuillez d'abord définir le dépôt de départ.")
        elif not st.session_state.stops:
            st.warning("Veuillez ajouter au moins un arrêt.")
        else:
            # Préparation des points pour l'API Google Maps
            # Inclut le dépôt comme origine, les arrêts comme waypoints, et le dépôt comme destination (pour certaines optimisations)
            
            # Séparation des livraisons et ramasses
            deliveries = [s for s in st.session_state.stops if s['type'] == 'Livraison']
            pickups_normal = [s for s in st.session_state.stops if s['type'] == 'Ramasse' and not s.get('force_on_departure')]
            pickups_forced = [s for s in st.session_state.stops if s['type'] == 'Ramasse' and s.get('force_on_departure')]
            
            ordered_stops = []
            route_poly_lines = []
            optimized_order_details = [] # Pour stocker les détails de l'ordre

            st.write("Calcul en cours...")
            
            # --- Logique d'Optimisation ---
            if st.session_state.mode_optimisation == "delivery_then_pickup":
                # 1. Optimiser les livraisons seules
                delivery_points_for_gmaps = [st.session_state.depot['address']] + [d['address'] for d in deliveries]
                if len(delivery_points_for_gmaps) > 1:
                    # On ne met le dépôt comme destination que s'il n'y a QUE des livraisons ou si on veut un retour explicite
                    # Ici, on optimise juste le chemin entre dépôts et livraisons
                    # Le calcul des directions retourne le chemin optimisé entre les points
                    route_result, waypoint_order = calculate_route(
                        [st.session_state.depot] + deliveries, # Utilise les dicts complets pour obtenir les coords
                        optimize_waypoints=True
                    )
                    
                    if route_result:
                        ordered_deliveries = [deliveries[i] for i in waypoint_order] if waypoint_order else deliveries
                        ordered_stops.extend(ordered_deliveries)
                        
                        # Ajouter les détails de cette partie de la route
                        route_details = get_route_details_for_stops(
                            [st.session_state.depot] + ordered_deliveries,
                            gmaps
                        )
                        route_poly_lines.extend([rd['polyline'] for rd in route_details])
                        for i, rd in enumerate(route_details):
                            optimized_order_details.append({
                                "address": rd['end_address'],
                                "type": ordered_deliveries[i]['type'],
                                "constraints": ordered_deliveries[i]['constraints'],
                                "distance_from_prev": rd['distance'],
                                "duration_from_prev": rd['duration'],
                                "route_polyline": rd['polyline']
                            })

                # 2. Optimiser les ramasses normales seules (après les livraisons)
                if pickups_normal:
                    # Pour les ramasses, on part du dernier point de livraison (ou dépôt si pas de livraisons)
                    last_point_after_deliveries = ordered_stops[-1] if ordered_stops else st.session_state.depot
                    
                    route_result_pickups, waypoint_order_pickups = calculate_route(
                        [last_point_after_deliveries] + pickups_normal,
                        optimize_waypoints=True
                    )
                    
                    if route_result_pickups:
                        ordered_pickups = [pickups_normal[i] for i in waypoint_order_pickups] if waypoint_order_pickups else pickups_normal
                        ordered_stops.extend(ordered_pickups)
                        
                        # Ajouter les détails de cette partie de la route
                        route_details_pickups = get_route_details_for_stops(
                            [last_point_after_deliveries] + ordered_pickups,
                            gmaps
                        )
                        route_poly_lines.extend([rd['polyline'] for rd in route_details_pickups])
                        for i, rd in enumerate(route_details_pickups):
                            optimized_order_details.append({
                                "address": rd['end_address'],
                                "type": ordered_pickups[i]['type'],
                                "constraints": ordered_pickups[i]['constraints'],
                                "distance_from_prev": rd['distance'],
                                "duration_from_prev": rd['duration'],
                                "route_polyline": rd['polyline']
                            })
                            
            elif st.session_state.mode_optimisation == "time_priority":
                # Logique complexe : intégrer les contraintes horaires en priorité
                # On utilise une approche où l'on essaie de regrouper les points
                # en respectant les contraintes, et en minimisant les temps d'attente.
                # C'est plus avancé et peut nécessiter une bibliothèque dédiée ou un algorithme plus sophistiqué.
                # Pour l'instant, on va simuler une priorité horaire basique :
                # 1. Livraisons (avec contraintes traitées en premier)
                # 2. Ramasses Forcées à l'aller
                # 3. Ramasses normales
                
                # Tri des points :
                # - Les points avec contraintes horaires (livraisons ou ramasses)
                # - Les ramasses forcées à l'aller
                # - Les ramasses normales
                
                # Pour simplifier, on va ordonner d'abord par type, puis on essaiera de réordonner les livraisons
                # en fonction des contraintes horaires.
                
                # Priorité 1: Ramasses Forcées
                ordered_stops.extend(pickups_forced)
                
                # Priorité 2: Livraisons (avec contraintes)
                # Tri des livraisons par heure d'ouverture si possible
                # Pour simplifier, on va les ajouter sans tri horaire complexe pour l'instant
                ordered_stops.extend(deliveries)
                
                # Priorité 3: Ramasses Normales
                ordered_stops.extend(pickups_normal)
                
                # Maintenant, on calcule la route avec cet ordre, et on laisse Google Maps optimiser les waypoints
                # NOTE: L'optimisation de Google Maps peut ne pas respecter parfaitement les contraintes horaires
                # si on ne les spécifie pas explicitement via departure_time et traffic_model.
                
                # Pour une vraie priorité horaire, il faudrait :
                # a) Récupérer les fenêtres horaires de chaque arrêt.
                # b) Calculer les temps de trajet entre chaque paire de points.
                # c) Utiliser un solveur d'optimisation (ex: OR-Tools) ou un algorithme
                #    spécifique pour trouver la séquence qui minimise les temps d'attente
                #    tout en respectant les contraintes.
                
                # Ici, on va utiliser l'ordre défini et laisser Google Maps faire le meilleur trajet possible
                # entre les points dans cet ordre (sans réordonner les waypoints pour ne pas perturber notre ordre).
                
                # Le `calculate_route` utilise `optimize_waypoints=True` par défaut.
                # Il faut donc le modifier pour qu'il utilise notre ordre prédéfini.
                
                # SOLUTION TEMPORAIRE: On recalcule les segments un par un avec notre ordre
                current_location_for_segment = st.session_state.depot
                for stop in ordered_stops:
                    try:
                        coords_current = get_coordinates(current_location_for_segment['address'], gmaps)
                        coords_next = get_coordinates(stop['address'], gmaps)
                        
                        if not coords_current or not coords_next: continue

                        # Récupération des contraintes pour ce point spécifique
                        stop_constraints = stop.get('constraints', '')
                        
                        # Tentative de calcul de l'heure d'arrivée estimée pour respecter les contraintes
                        # Ceci est une simplification. Une vraie solution nécessiterait un algorithme plus poussé.
                        estimated_arrival = datetime.now() # Heure de départ
                        if "fenêtre horaire" in stop_constraints.lower():
                            # Extraire la fenêtre horaire (ex: "10:00-11:00") - ceci est une simplification
                            # Il faudrait un parser plus robuste
                            parts = stop_constraints.split(' - ')
                            if len(parts) == 2 and ':' in parts[0] and ':' in parts[1]:
                                try:
                                    start_time_str, end_time_str = parts[0].strip(), parts[1].strip()
                                    # On assume que c'est pour aujourd'hui, ce qui est une grosse simplification
                                    today = datetime.now().date()
                                    window_start = datetime.combine(today, datetime.strptime(start_time_str, "%H:%M").time())
                                    window_end = datetime.combine(today, datetime.strptime(end_time_str, "%H:%M").time())
                                    
                                    # Calculer la durée du trajet actuel pour estimer l'arrivée
                                    directions_segment = gmaps.directions(
                                        coords_current, coords_next, mode="driving", departure_time=estimated_arrival
                                    )
                                    if directions_segment:
                                        segment_duration_value = directions_segment[0]['legs'][0]['duration']['value']
                                        estimated_arrival += timedelta(seconds=segment_duration_value)
                                        
                                        # Ajuster si on arrive trop tôt
                                        if estimated_arrival < window_start:
                                            wait_time = window_start - estimated_arrival
                                            estimated_arrival = window_start # On attend jusqu'à l'heure d'ouverture
                                            st.info(f"Attente estimée à {stop['address']} : {wait_time}")
                                        
                                        # Si on arrive trop tard, on affiche une alerte
                                        if estimated_arrival > window_end:
                                            st.warning(f"Arrivée potentiellement trop tard à {stop['address']} (fenêtre : {start_time_str}-{end_time_str})")

                                except ValueError:
                                    pass # Ne pas gérer si le format horaire est mauvais

                        # Calculer le segment de route
                        # On ne demande PAS à Google de réordonner les waypoints
                        route_result_segment = gmaps.directions(
                            coords_current,
                            coords_next,
                            mode="driving",
                            departure_time=estimated_arrival, # Utiliser l'heure d'arrivée ajustée si nécessaire
                            optimize_waypoints=False # Crucial pour garder notre ordre
                        )

                        if route_result_segment:
                            leg = route_result_segment[0]['legs'][0]
                            distance_text = leg['distance']['text']
                            duration_text = leg['duration']['text']
                            encoded_polyline = route_result_segment[0]['overview_polyline']['points']
                            
                            # Mise à jour de l'heure pour le prochain segment
                            # On ajoute la durée du trajet + durée de visite estimée (simplifié ici)
                            duration_value = leg['duration']['value']
                            # Ici, il faudrait aussi ajouter la durée de visite si spécifiée dans les contraintes
                            # Pour l'instant, on ajoute juste un petit délai
                            estimated_arrival += timedelta(seconds=duration_value + 60) # +60s marge
                            
                            route_poly_lines.append(encoded_polyline)
                            optimized_order_details.append({
                                "address": stop['address'],
                                "type": stop['type'],
                                "constraints": stop['constraints'],
                                "distance_from_prev": distance_text,
                                "duration_from_prev": duration_text,
                                "route_polyline": encoded_polyline,
                                "estimated_arrival": estimated_arrival.strftime("%H:%M") if estimated_arrival else "N/A"
                            })
                            
                            current_location_for_segment = stop # Le point de départ du prochain segment est ce point
                        else:
                            st.warning(f"Aucun itinéraire trouvé pour le segment: {current_location_for_segment['address']} -> {stop['address']}")
                            
                    except Exception as e:
                        st.error(f"Erreur lors du calcul du segment {current_location_for_segment['address']} -> {stop['address']} : {e}")
                        
            elif st.session_state.mode_optimisation == "gmaps_optimize_full_route":
                # Option la plus simple : laisser Google optimiser tout le trajet Dépôt -> Points -> Dépôt
                all_points_coords = [st.session_state.depot] + st.session_state.stops
                
                # Créer la liste des waypoints (tous les arrêts)
                waypoints_for_gmaps = [p['address'] for p in st.session_state.stops]
                
                # Utiliser la fonction calculate_route qui gère l'optimisation des waypoints
                route_result, waypoint_order = calculate_route(
                    all_points_coords, # Utilise la liste complète y compris dépôt
                    optimize_waypoints=True # Demande l'optimisation
                )
                
                if route_result:
                    # Réordonner les arrêts selon l'ordre retourné par Google Maps
                    # Le waypoint_order s'applique aux waypoints passés, donc aux stops.
                    ordered_stops = [st.session_state.stops[i] for i in waypoint_order]
                    
                    # Calculer les segments détaillés avec le nouvel ordre
                    route_details = get_route_details_for_stops(
                        [st.session_state.depot] + ordered_stops,
                        gmaps
                    )
                    route_poly_lines = [rd['polyline'] for rd in route_details]
                    for i, rd in enumerate(route_details):
                        optimized_order_details.append({
                            "address": rd['end_address'],
                            "type": ordered_stops[i]['type'],
                            "constraints": ordered_stops[i]['constraints'],
                            "distance_from_prev": rd['distance'],
                            "duration_from_prev": rd['duration'],
                            "route_polyline": rd['polyline']
                        })

            # Si l'optimisation a réussi (ou si on a calculé les segments)
            if ordered_stops and optimized_order_details:
                st.success("Tournée optimisée !")
                
                # Afficher le résumé de la tournée
                st.subheader("Résumé de la Tournée Optimisée")
                
                # Calculer le total
                total_distance_value = 0
                total_duration_value = 0
                
                # Inclure le trajet retour au dépôt
                last_stop_address = ordered_stops[-1]['address']
                depot_address_val = st.session_state.depot['address']

                try:
                    # Debug pour la dernière étape du trajet
                    now_for_return = datetime.now() # Réinitialiser pour le calcul du retour
                    # On estime l'heure d'arrivée au dernier arrêt pour avoir un 'departure_time' plus réaliste
                    # Ceci est une grosse simplification, idéalement on somme les durées
                    current_time_sum = timedelta()
                    for detail in optimized_order_details:
                         # Convertir la durée string en timedelta (approximatif)
                         parts = detail['duration_from_prev'].replace('hours', 'hr').replace('mins', 'min').split()
                         for part in parts:
                             if 'hr' in part: current_time_sum += timedelta(hours=int(part.replace('hr','')))
                             if 'min' in part: current_time_sum += timedelta(minutes=int(part.replace('min','')))
                    
                    # Tentative de calcul de l'heure d'arrivée au dernier point pour le retour
                    # Ceci est une approximation
                    estimated_arrival_at_last_stop = datetime.now() + current_time_sum
                    
                    directions_return = gmaps.directions(
                        last_stop_address,
                        depot_address_val,
                        mode="driving",
                        departure_time=estimated_arrival_at_last_stop, # Partir quand on finit la dernière mission
                        optimize_waypoints=False
                    )
                    
                    if directions_return:
                        leg_return = directions_return[0]['legs'][0]
                        distance_return_text = leg_return['distance']['text']
                        duration_return_text = leg_return['duration']['text']
                        polyline_return = directions_return[0]['overview_polyline']['points']
                        route_poly_lines.append(polyline_return)
                        
                        # Calcul des totaux
                        total_distance_value += leg_return['distance']['value']
                        total_duration_value += leg_return['duration']['value']
                        
                        # Ajouter les totaux des segments précédents
                        for detail in optimized_order_details:
                            # Conversion approximative des durées textuelles en secondes
                            # Ceci est une simplification, il faudrait parser le texte précisément
                            # ou stocker les valeurs numériques directement.
                            try:
                                parts = detail['duration_from_prev'].replace('hours', 'hr').replace('mins', 'min').split()
                                seg_duration_secs = 0
                                for part in parts:
                                    if 'hr' in part: seg_duration_secs += int(part.replace('hr','')) * 3600
                                    if 'min' in part: seg_duration_secs += int(part.replace('min','')) * 60
                                total_duration_value += seg_duration_secs
                            except: pass # Ignorer si la conversion échoue
                            
                            # Pour la distance, on aurait aussi besoin de la convertir si elle est en texte
                            # Mais on peut supposer qu'on a les valeurs numériques si nécessaire

                        st.write(f"**Distance totale :** {distance_return_text} (incluant le retour au dépôt)")
                        st.write(f"**Durée totale estimée :** {duration_return_text} (incluant le retour au dépôt)")
                        
                    else:
                        st.warning("Impossible de calculer le trajet retour au dépôt.")

                except Exception as e:
                    st.error(f"Erreur lors du calcul du trajet retour au dépôt : {e}")


                # Affichage détaillé des arrêts ordonnés
                st.subheader("Ordre des Arrêts")
                
                # Créer la liste complète des arrêts incluant le dépôt comme point de départ
                full_ordered_route = [st.session_state.depot] + ordered_stops
                
                col_order_num, col_order_addr, col_order_type, col_order_constraints, col_order_dist, col_order_dur, col_order_arrival = st.columns([0.5, 3, 1, 1.5, 1, 1, 1])
                col_order_num.markdown("**#**")
                col_order_addr.markdown("**Adresse**")
                col_order_type.markdown("**Type**")
                col_order_constraints.markdown("**Contraintes**")
                col_order_dist.markdown("**Dist. (Préc.)**")
                col_order_dur.markdown("**Durée (Préc.)**")
                col_order_arrival.markdown("**Arrivée (Est.)**")

                for i, stop_info in enumerate(optimized_order_details):
                    num = i + 1
                    col_order_num.write(f"{num}.")
                    col_order_addr.write(stop_info['address'])
                    
                    display_type = stop_info['type']
                    if stop_info['type'] == "Ramasse" and st.session_state.stops[i]['force_on_departure']: # Accéder aux données originales pour la flag
                        display_type += " (Forcée)"
                    col_order_type.write(display_type)
                    
                    col_order_constraints.write(stop_info['constraints'])
                    col_order_dist.write(stop_info.get('distance_from_prev', '-'))
                    col_order_dur.write(stop_info.get('duration_from_prev', '-'))
                    col_order_arrival.write(stop_info.get('estimated_arrival', '-'))

                # --- CARTE DE LA TOURNEE ---
                st.subheader("Carte de la Tournée")

                # Calculer le centre de la carte
                center_lat = st.session_state.depot['latitude'] if st.session_state.depot else 0
                center_lon = st.session_state.depot['longitude'] if st.session_state.depot else 0
                if st.session_state.stops:
                    # Moyenne des latitudes et longitudes pour centrer la carte
                    all_lats = [st.session_state.depot['latitude']] + [s['latitude'] for s in st.session_state.stops]
                    all_lons = [st.session_state.depot['longitude']] + [s['longitude'] for s in st.session_state.stops]
                    center_lat = sum(all_lats) / len(all_lats)
                    center_lon = sum(all_lons) / len(all_lons)

                m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

                # Ajouter le dépôt
                folium.Marker(
                    location=[st.session_state.depot['latitude'], st.session_state.depot['longitude']],
                    popup=f"Dépôt: {st.session_state.depot['address']}",
                    icon=folium.Icon(color='darkblue', icon='home')
                ).add_to(m)

                # Ajouter les arrêts et tracer les lignes
                previous_coords = [st.session_state.depot['latitude'], st.session_state.depot['longitude']]
                
                for i, stop in enumerate(ordered_stops):
                    stop_coords = [stop['latitude'], stop['longitude']]
                    
                    # Icônes personnalisées
                    icon_color = 'blue' # Livraison
                    icon_type = 'info-sign' # Livraison
                    if stop['type'] == 'Ramasse':
                        icon_color = 'orange'
                        icon_type = 'cloud-upload' # Ramasse
                        if stop.get('force_on_departure'):
                            icon_color = 'red' # Ramasse forcée
                            icon_type = 'cloud-download' # Ramasse forcée

                    folium.Marker(
                        location=stop_coords,
                        popup=f"<b>{stop['address']}</b><br>{stop['type']}<br>Contraintes: {stop['constraints']}",
                        icon=folium.Icon(color=icon_color, icon=icon_type)
                    ).add_to(m)

                    # Tracer la ligne du segment précédent
                    # On utilise les polylines récupérées lors du calcul des directions
                    if i < len(route_poly_lines):
                        PolyLine(
                            locations=polyline_lib.decode(route_poly_lines[i]),
                            color=icon_color, # Utiliser la même couleur que le marqueur de destination
                            weight=5,
                            opacity=0.7,
                            popup=f"Trajet vers {stop['address']}<br>{optimized_order_details[i].get('distance_from_prev', '')}<br>{optimized_order_details[i].get('duration_from_prev', '')}"
                        ).add_to(m)
                    
                    previous_coords = stop_coords # Mettre à jour pour le prochain segment

                # Afficher la carte
                folium_static(m, width=1000, height=500)
            else:
                st.warning("Impossible de calculer la tournée avec les données fournies. Vérifiez les erreurs.")

# --- EXPLICATION DES MODES D'OPTIMISATION (optionnel) ---
st.sidebar.subheader("Aide sur les Modes d'Optimisation")
st.sidebar.markdown("""
- **Livraisons avant Ramasses :** Optimise d'abord le trajet des livraisons, puis celui des ramasses. Utile si vous devez vider le camion avant de collecter.
- **Priorité Horaire :** Tente de minimiser les temps d'attente aux fenêtres horaires spécifiées. Plus complexe, nécessite des fenêtres horaires précises.
- **Optimisation par Google Maps :** Laisse Google Maps décider du meilleur ordre des arrêts pour minimiser le temps total du trajet Dépôt -> Tous les Points -> Dépôt.
""")

# --- EXPLICATION SUR LES RAMASSES FORCÉES ---
st.sidebar.subheader("Ramasses Forcées à l'Aller")
st.sidebar.markdown("""
Cocher cette case pour une ramasse indique à l'algorithme de la traiter comme une livraison dans le trajet aller.
Elle sera toujours affichée comme une ramasse, mais sa position dans le calcul sera plus proche du début de la tournée.
Utile si le client a spécifiquement besoin que vous passiez tôt pour récupérer un objet.
""")

# --- SECTION FOOTER ---
st.markdown("---")
st.markdown("Développé avec ❤️ par [Votre Nom/Équipe]")
