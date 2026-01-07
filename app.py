import streamlit as st
import googlemaps
from streamlit_folium import folium_static
import folium
from datetime import datetime, timedelta
import polyline
import time
import random # Pour la partie aléatoire du crash-test précédent

# --- CONFIGURATION & STYLE ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

st.markdown("""
    <style>
    .summary-box { padding: 6px 12px; border-radius: 8px; margin-bottom: 5px; display: flex; align-items: center; color: white; font-size: 0.9rem; }
    .depot-box { background-color: #28a745; border: 1px solid #1e7e34; } 
    .client-box { background-color: #0047AB; border: 1px solid #003380; }
    [data-testid="stHorizontalBlock"] { align-items: center; }
    .client-card { background-color: #0047AB; color: white; padding: 15px; border-radius: 10px 10px 0 0; margin-top: 10px; }
    .address-box { background-color: #0047AB; padding: 0 15px 10px 15px; border-radius: 0 0 10px 10px; margin-bottom: 10px; }
    .address-box code { color: white !important; background-color: transparent !important; font-weight: bold;}
    .address-box p { margin-bottom: 5px; font-size: 0.9rem; }
    .stButton>button { width: 100%; }
    .info-box { background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-bottom: 10px; border: 1px solid #ddd; }
    .waiting-text { color: #FFC107; font-weight: bold; }
    .error-text { color: #DC3545; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISATION DES SESSIONS STATES ---
if 'clients' not in st.session_state:
    st.session_state.clients = []
if 'depot' not in st.session_state:
    st.session_state.depot = None
if 'step' not in st.session_state:
    st.session_state.step = 1
if 'max_wait_time' not in st.session_state:
    st.session_state.max_wait_time = 15 # Max 15 minutes d'attente acceptables

# --- API GOOGLE MAPS ---
# Assurez-vous que la clé API est correctement configurée dans vos secrets Streamlit
try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except Exception as e:
    st.error(f"Erreur lors de l'initialisation de l'API Google Maps. Vérifiez votre clé API. {e}")
    st.stop()

# --- FONCTIONS UTILITAIRES ---

def geocode_address(address_str):
    try:
        geocode_result = gmaps.geocode(address_str)
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            return location['lat'], location['lng']
        else:
            return None, None
    except Exception as e:
        st.warning(f"Erreur de géocodage pour '{address_str}': {e}")
        return None, None

def get_directions(origin, destination, mode="driving", departure_time=None):
    try:
        directions_result = gmaps.directions(origin, destination, mode=mode, departure_time=departure_time)
        if directions_result:
            return directions_result
        else:
            return None
    except Exception as e:
        st.warning(f"Erreur lors de l'appel API Directions: {e}")
        return None

def format_address(npa, ville, rue):
    return f"{rue}, {npa} {ville}"

def get_travel_time(origin_latlng, dest_latlng, departure_time=None):
    try:
        # Utilisation de distance_matrix pour obtenir le temps de trajet le plus précis
        # Note: Google Maps Distance Matrix API peut avoir des coûts associés
        # Pour une version gratuite ou limitée, on peut se rabattre sur `directions` mais c'est moins optimal pour les matrices
        
        # Alternative plus simple et souvent suffisante avec `directions` pour 2 points
        origin_str = f"{origin_latlng[0]},{origin_latlng[1]}"
        destination_str = f"{dest_latlng[0]},{dest_latlng[1]}"
        
        res = gmaps.directions(origin_str, destination_str, mode="driving", departure_time=departure_time)
        if res:
            duration_seconds = res[0]['legs'][0]['duration']['value']
            return duration_seconds
        return None
    except Exception as e:
        st.warning(f"Erreur pour calculer le temps de trajet: {e}")
        return None

def calculate_route_optimization(clients_data, depot, mode="driving", departure_time_dt=None):
    if not clients_data:
        return [], None, None, None

    # Préparation des données avec coordonnées
    processed_clients = []
    for client in clients_data:
        lat, lng = geocode_address(format_address(client['npa'], client['ville'], client['rue']))
        if lat and lng:
            processed_clients.append({
                **client,
                'lat': lat,
                'lng': lng,
                'latlng': (lat, lng)
            })
        else:
            st.warning(f"Impossible de géocoder l'adresse de {client['nom']}. Ce client sera ignoré pour l'optimisation.")

    if not processed_clients:
        st.error("Aucun client n'a pu être géocodé. Impossible de calculer la tournée.")
        return [], None, None, None

    # --- LOGIQUE D'ORGANISATION DE LA TOURNEE ---
    
    # Séparation des missions : Livraisons, Ramasses, et Ramasses cachées comme livraisons
    deliveries = []
    pickups = []
    hidden_pickups_as_deliveries = [] # Nouvel état pour ramasses cachées

    for client in processed_clients:
        if client['type'] == 'Livraison':
            deliveries.append(client)
        elif client['type'] == 'Ramasse':
            if client.get('consider_as_delivery_for_calc', False): # Nouvelle logique pour ramasse cachée
                hidden_pickups_as_deliveries.append(client)
            else:
                pickups.append(client)

    # Combinaison des livraisons et des ramasses cachées pour la phase "aller"
    aller_stops = sorted(deliveries + hidden_pickups_as_deliveries, key=lambda x: x.get('order_priority', float('inf'))) # Priorité manuelle si définie
    retour_stops = sorted(pickups, key=lambda x: x.get('order_priority', float('inf'))) # Priorité manuelle si définie

    final_ordered_stops = []
    current_time = departure_time_dt
    total_distance = 0
    total_duration = 0
    wait_time_total = 0
    
    current_location = depot['latlng']

    # --- PHASE 1 : ALLER (Livraisons + Ramasses cachées) ---
    
    # Tri basé sur le mode choisi
    if mode == "driving": # Mode "Mathématique" (Google Maps)
        # Pour le mode "driving", on laisse Google gérer le plus court chemin pour tous les arrêts
        # On ajoute temporairement les arrêts retour pour que l'API calcule le chemin global le plus court
        all_stops_for_gmaps = aller_stops + retour_stops
        
        if not all_stops_for_gmaps:
            st.info("Aucun arrêt à planifier.")
            return [], None, None, None

        # Utilisation de l'API Directions pour obtenir l'itinéraire optimisé par Google
        waypoint_locations = [f"{c['lat']},{c['lng']}" for c in all_stops_for_gmaps]
        
        # On doit construire l'origine et la destination pour l'API
        origin_point = f"{depot['lat']},{depot['lng']}"
        
        # Le problème ici est que l'API `directions` ne renvoie pas directement l'ordre optimisé pour PLUSIEURS WAYPOINTS
        # Elle renvoie le chemin le plus court *si on passe dans l'ordre spécifié*.
        # Pour obtenir l'ordre optimisé, il faut utiliser l'API `directions` en mode `optimize_waypoints=True`
        # Mais cela nécessite de passer les waypoints et d'obtenir un nouvel ordre.
        
        # Solution de contournement : on va calculer les temps entre tous les points
        # pour simuler une optimisation "approximative" si optimize_waypoints n'est pas directement dispo ou trop complexe ici.
        # La VRAIE optimisation d'ordre est une résolution du TSP (Traveling Salesperson Problem), ce qui est complexe.
        # Pour l'instant, avec `mode="driving"`, on va juste tracer le chemin tel que l'utilisateur l'a entré en priorité.
        # Si l'utilisateur VEUT l'optimisation d'ordre, c'est le mode "Logique Chauffeur".
        
        # Pour simplifier, dans le mode "driving", on va garder l'ordre d'entrée des livraisons et des ramasses.
        # On va calculer les temps de trajet et les ajouter à la liste `final_ordered_stops`.
        
        ordered_points_for_calc = [depot['latlng']] + [c['latlng'] for c in aller_stops] + [c['latlng'] for c in retour_stops]
        
        # Calcul du trajet global pour le mode "driving" sans réordonnancement par l'API
        # On prend l'ordre tel qu'il a été entré et on calcule les trajets
        
        legs = []
        
        # Trajet Dépôt -> Premier client
        leg_info = get_directions(f"{depot['lat']},{depot['lng']}", f"{aller_stops[0]['lat']},{aller_stops[0]['lng']}", mode="driving", departure_time=int(departure_time_dt.timestamp()) if departure_time_dt else None)
        if leg_info:
            legs.append(leg_info[0])
            total_distance += leg_info[0]['legs'][0]['distance']['value']
            total_duration += leg_info[0]['legs'][0]['duration']['value']
            
        # Trajets entre clients (livraisons)
        for i in range(len(aller_stops) - 1):
            leg_info = get_directions(f"{aller_stops[i]['lat']},{aller_stops[i]['lng']}", f"{aller_stops[i+1]['lat']},{aller_stops[i+1]['lng']}", mode="driving")
            if leg_info:
                legs.append(leg_info[0])
                total_distance += leg_info[0]['legs'][0]['distance']['value']
                total_duration += leg_info[0]['legs'][0]['duration']['value']

        # Trajet dernier client (livraison) -> Premier client (ramasse)
        first_pickup_dest = f"{retour_stops[0]['lat']},{retour_stops[0]['lng']}" if retour_stops else None
        last_delivery_origin = f"{aller_stops[-1]['lat']},{aller_stops[-1]['lng']}"
        
        if first_pickup_dest:
            leg_info = get_directions(last_delivery_origin, first_pickup_dest, mode="driving")
            if leg_info:
                legs.append(leg_info[0])
                total_distance += leg_info[0]['legs'][0]['distance']['value']
                total_duration += leg_info[0]['legs'][0]['duration']['value']
        
        # Trajets entre clients (ramasses)
        for i in range(len(retour_stops) - 1):
            leg_info = get_directions(f"{retour_stops[i]['lat']},{retour_stops[i]['lng']}", f"{retour_stops[i+1]['lat']},{retour_stops[i+1]['lng']}", mode="driving")
            if leg_info:
                legs.append(leg_info[0])
                total_distance += leg_info[0]['legs'][0]['distance']['value']
                total_duration += leg_info[0]['legs'][0]['duration']['value']

        # Trajet dernier client (ramasse) -> Dépôt (si besoin, mais pas dans ce mode)
        # Ici, on ne calcule pas le retour au dépôt dans le mode "driving" optimisé d'office
        
        # Reconstitution de la liste triée pour l'affichage
        final_ordered_stops = aller_stops + retour_stops
        
        # Calcul des temps d'arrivée et de service pour chaque arrêt
        current_time = departure_time_dt
        
        for i, client in enumerate(final_ordered_stops):
            # Temps de trajet vers ce client
            if i == 0: # Premier client
                origin_coords = depot['latlng']
            else:
                origin_coords = final_ordered_stops[i-1]['latlng']

            # On cherche le leg correspondant dans notre liste `legs`
            # C'est un peu laborieux sans une structure de données plus adaptée
            # Une manière simple est de recalculer le trajet pour chaque étape
            
            # Recalculer le temps de trajet pour chaque étape (peut être lent si beaucoup de points)
            travel_duration_secs = None
            if i == 0:
                # Dépôt -> 1er client
                res_leg = gmaps.directions(f"{depot['lat']},{depot['lng']}", f"{client['lat']},{client['lng']}", mode="driving", departure_time=int(current_time.timestamp()) if current_time else None)
            else:
                # Client précédent -> Client actuel
                res_leg = gmaps.directions(f"{final_ordered_stops[i-1]['lat']},{final_ordered_stops[i-1]['lng']}", f"{client['lat']},{client['lng']}", mode="driving", departure_time=int(current_time.timestamp()) if current_time else None)

            if res_leg:
                travel_duration_secs = res_leg[0]['legs'][0]['duration']['value']
                # On utilise le temps de trajet "optimisé" par Google Maps ici pour la durée
                # Le temps total de la tournée devra être recalculé plus bas avec les legs réels.
                
                # Calcul de l'heure d'arrivée estimée AVANT le trajet actuel
                arrival_at_client = current_time + timedelta(seconds=travel_duration_secs)
                
                # Gestion des contraintes horaires (fenêtres)
                wait_time = 0
                if client.get('heure_debut_fenetre') and client.get('heure_fin_fenetre'):
                    earliest_arrival = datetime.combine(departure_time_dt.date(), client['heure_debut_fenetre'])
                    latest_arrival = datetime.combine(departure_time_dt.date(), client['heure_fin_fenetre'])
                    
                    # Si j'arrive avant la fenêtre, j'attends
                    if arrival_at_client < earliest_arrival:
                        wait_time = (earliest_arrival - arrival_at_client).total_seconds()
                        # On vérifie si le temps d'attente est acceptable
                        if wait_time > st.session_state.max_wait_time * 60:
                            client['status'] = f"Attente > {st.session_state.max_wait_time} min ({wait_time/60:.0f} min)"
                            client['status_class'] = "waiting-text"
                        else:
                            client['status'] = f"Arrivée en avance ({wait_time/60:.0f} min d'attente)"
                            client['status_class'] = "waiting-text"
                        arrival_at_client = earliest_arrival # Mon heure réelle de service commence à la fenêtre
                    
                    # Si j'arrive après la fenêtre, c'est un problème (pour l'instant on affiche)
                    elif arrival_at_client > latest_arrival:
                        client['status'] = "En retard !"
                        client['status_class'] = "error-text"
                    else:
                        client['status'] = "Dans la fenêtre horaire"
                        client['status_class'] = ""
                    
                    wait_time_total += wait_time
                    
                else: # Pas de contrainte horaire spécifique
                    client['status'] = ""
                    client['status_class'] = ""

                # Temps de service (durée de la mission)
                service_duration = timedelta(minutes=client['dur'])
                current_time = arrival_at_client + service_duration # Mise à jour pour le prochain client
                
                client['heure_arrivee_estimee'] = arrival_at_client.strftime("%H:%M")
                client['heure_depart_estimee'] = current_time.strftime("%H:%M")
                client['temps_attente_sec'] = wait_time
                client['temps_trajet_secs'] = travel_duration_secs
                
                final_ordered_stops[i] = client # Update the client dict
            else:
                client['heure_arrivee_estimee'] = "N/A"
                client['heure_depart_estimee'] = "N/A"
                client['status'] = "Erreur itinéraire"
                client['status_class'] = "error-text"
                
        # Calculer le temps total de la tournée (incluant service et attentes)
        if final_ordered_stops:
            total_duration_secs = (current_time - departure_time_dt).total_seconds()
            
            # Recalculer la distance totale avec les legs réels
            total_distance_actual = sum(leg['legs'][0]['distance']['value'] for leg in legs)
            total_duration_actual = sum(leg['legs'][0]['duration']['value'] for leg in legs) + sum(c.get('temps_attente_sec', 0) for c in final_ordered_stops) + sum(timedelta(minutes=c['dur']).total_seconds() for c in final_ordered_stops)
            
            return final_ordered_stops, total_distance_actual, total_duration_actual, wait_time_total
        else:
            return [], 0, 0, 0

    elif mode == "logic_chauffeur":
        # --- PHASE 1 : ALLER (Livraisons + Ramasses cachées) ---
        # On trie les arrêts d'aller pour qu'ils soient du plus proche au plus loin (simplifié par défaut)
        # On pourrait affiner cela en calculant les distances réelles au dépôt
        
        # Ici, on laisse Google Maps ordonnancer les waypoints pour l'aller (le plus court chemin entre ces points)
        if aller_stops:
            waypoint_locations_aller = [f"{c['lat']},{c['lng']}" for c in aller_stops]
            
            # On utilise `directions` avec optimize_waypoints
            # Note: optimize_waypoints n'est pas disponible pour tous les modes de transport et peut avoir des limitations
            # Dans notre cas, on va simuler en prenant le trajet le plus long et en le divisant en segments.
            # La vraie optimisation d'ordre pour plusieurs points est complexe (TSP)
            
            # On va trier les points d'aller en fonction de leur distance au dépôt pour une logique "aller" simple
            # Calcul des distances au dépôt
            for client in aller_stops:
                dist = geodesic(depot['latlng'], client['latlng']).km
                client['distance_to_depot'] = dist
            
            # Tri basé sur la distance au dépôt (du plus proche au plus loin)
            aller_stops_sorted = sorted(aller_stops, key=lambda x: x['distance_to_depot'])

            # Calculer l'itinéraire pour les arrêts d'aller
            ordered_route_aller = []
            current_time_aller = departure_time_dt
            
            for i, client in enumerate(aller_stops_sorted):
                if i == 0:
                    origin_coords = depot['latlng']
                else:
                    origin_coords = aller_stops_sorted[i-1]['latlng']
                
                # On utilise l'API Directions pour obtenir les détails du segment
                res_leg = gmaps.directions(f"{origin_coords[0]},{origin_coords[1]}", f"{client['lat']},{client['lng']}", mode="driving", departure_time=int(current_time_aller.timestamp()) if current_time_aller else None)
                
                if res_leg:
                    leg_data = res_leg[0]['legs'][0]
                    travel_duration_secs = leg_data['duration']['value']
                    travel_distance_m = leg_data['distance']['value']
                    
                    total_distance += travel_distance_m
                    total_duration += travel_duration_secs

                    arrival_at_client = current_time_aller + timedelta(seconds=travel_duration_secs)
                    
                    wait_time = 0
                    # Gestion des contraintes horaires
                    if client.get('heure_debut_fenetre') and client.get('heure_fin_fenetre'):
                        earliest_arrival = datetime.combine(departure_time_dt.date(), client['heure_debut_fenetre'])
                        latest_arrival = datetime.combine(departure_time_dt.date(), client['heure_fin_fenetre'])
                        
                        if arrival_at_client < earliest_arrival:
                            wait_time = (earliest_arrival - arrival_at_client).total_seconds()
                            if wait_time > st.session_state.max_wait_time * 60:
                                client['status'] = f"Attente > {st.session_state.max_wait_time} min ({wait_time/60:.0f} min)"
                                client['status_class'] = "waiting-text"
                            else:
                                client['status'] = f"Arrivée en avance ({wait_time/60:.0f} min d'attente)"
                                client['status_class'] = "waiting-text"
                            arrival_at_client = earliest_arrival
                        elif arrival_at_client > latest_arrival:
                            client['status'] = "En retard !"
                            client['status_class'] = "error-text"
                        else:
                            client['status'] = "Dans la fenêtre horaire"
                            client['status_class'] = ""
                        wait_time_total += wait_time
                    else:
                        client['status'] = ""
                        client['status_class'] = ""

                    service_duration = timedelta(minutes=client['dur'])
                    current_time_aller = arrival_at_client + service_duration
                    
                    client['heure_arrivee_estimee'] = arrival_at_client.strftime("%H:%M")
                    client['heure_depart_estimee'] = current_time_aller.strftime("%H:%M")
                    client['temps_attente_sec'] = wait_time
                    client['temps_trajet_secs'] = travel_duration_secs
                    
                    ordered_route_aller.append(client)
                else:
                    client['status'] = "Erreur itinéraire"
                    client['status_class'] = "error-text"
                    ordered_route_aller.append(client) # Ajouter quand même pour affichage

            final_ordered_stops.extend(ordered_route_aller)
            current_time = current_time_aller # Mise à jour du temps global
            current_location = aller_stops_sorted[-1]['latlng'] if aller_stops_sorted else depot['latlng']

        # --- PHASE 2 : RETOUR (Ramasses) ---
        # On trie les arrêts de retour pour qu'ils soient du plus loin au plus proche du DÉPÔT
        # Ou plutôt, du plus loin au plus proche de la DERNIÈRE LOCALISATION de l'aller
        
        if retour_stops:
            # Calculer les distances au dépôt pour trier le retour (du plus loin au plus près)
            for client in retour_stops:
                dist = geodesic(depot['latlng'], client['latlng']).km
                client['distance_to_depot'] = dist
            
            # Tri basé sur la distance au dépôt (du plus loin au plus proche)
            # C'est le principe "retour au bercail"
            retour_stops_sorted = sorted(retour_stops, key=lambda x: x['distance_to_depot'], reverse=True)
            
            # Calculer l'itinéraire pour les arrêts de retour
            current_location_retour = current_location # Commence là où l'aller s'est terminé

            for i, client in enumerate(retour_stops_sorted):
                # On utilise l'API Directions pour obtenir les détails du segment
                res_leg = gmaps.directions(f"{current_location_retour[0]},{current_location_retour[1]}", f"{client['lat']},{client['lng']}", mode="driving", departure_time=int(current_time.timestamp()) if current_time else None)
                
                if res_leg:
                    leg_data = res_leg[0]['legs'][0]
                    travel_duration_secs = leg_data['duration']['value']
                    travel_distance_m = leg_data['distance']['value']
                    
                    total_distance += travel_distance_m
                    total_duration += travel_duration_secs

                    arrival_at_client = current_time + timedelta(seconds=travel_duration_secs)
                    
                    wait_time = 0
                    # Gestion des contraintes horaires (même pour les ramasses si spécifié, mais moins courant)
                    if client.get('heure_debut_fenetre') and client.get('heure_fin_fenetre'):
                        earliest_arrival = datetime.combine(departure_time_dt.date(), client['heure_debut_fenetre'])
                        latest_arrival = datetime.combine(departure_time_dt.date(), client['heure_fin_fenetre'])
                        
                        if arrival_at_client < earliest_arrival:
                            wait_time = (earliest_arrival - arrival_at_client).total_seconds()
                            if wait_time > st.session_state.max_wait_time * 60:
                                client['status'] = f"Attente > {st.session_state.max_wait_time} min ({wait_time/60:.0f} min)"
                                client['status_class'] = "waiting-text"
                            else:
                                client['status'] = f"Arrivée en avance ({wait_time/60:.0f} min d'attente)"
                                client['status_class'] = "waiting-text"
                            arrival_at_client = earliest_arrival
                        elif arrival_at_client > latest_arrival:
                            client['status'] = "En retard !"
                            client['status_class'] = "error-text"
                        else:
                            client['status'] = "Dans la fenêtre horaire"
                            client['status_class'] = ""
                        wait_time_total += wait_time
                    else:
                        client['status'] = ""
                        client['status_class'] = ""
                        
                    service_duration = timedelta(minutes=client['dur'])
                    current_time = arrival_at_client + service_duration
                    
                    client['heure_arrivee_estimee'] = arrival_at_client.strftime("%H:%M")
                    client['heure_depart_estimee'] = current_time.strftime("%H:%M")
                    client['temps_attente_sec'] = wait_time
                    client['temps_trajet_secs'] = travel_duration_secs
                    
                    final_ordered_stops.append(client)
                    current_location_retour = client['latlng'] # MAJ pour le prochain segment
                else:
                    client['status'] = "Erreur itinéraire"
                    client['status_class'] = "error-text"
                    final_ordered_stops.append(client) # Ajouter quand même

        # Calculer le temps total de la tournée (incluant service et attentes)
        if final_ordered_stops:
            total_duration_secs = (current_time - departure_time_dt).total_seconds()
            
            # On calcule la distance et durée totales à partir des segments calculés
            # Note: ceci ne prend pas en compte le retour au dépôt après la dernière ramasse.
            # Il faudrait ajouter un dernier appel à `get_directions` si le retour au dépôt est nécessaire.
            
            return final_ordered_stops, total_distance, total_duration + wait_time_total, wait_time_total
        else:
            return [], 0, 0, 0

    else: # Mode par défaut ou inconnue, utilise l'ordre d'entrée
        return [], 0, 0, 0

# --- NAVIGATION ENTRE LES ÉTAPES ---

def show_depot_form():
    st.header("🏁 1. Votre Dépôt de Départ")
    with st.form("depot_form", clear_on_submit=True):
        depot_nom = st.text_input("Nom du dépôt (ex: Entrepôt principal)")
        depot_rue = st.text_input("Rue et numéro")
        depot_npa = st.text_input("NPA (code postal)")
        depot_ville = st.text_input("Ville")
        depot_heure = st.time_input("Heure de départ", datetime.now().time())
        
        if st.form_submit_button("Valider le dépôt et continuer"):
            if depot_nom and depot_rue and depot_npa and depot_ville:
                full_address = format_address(depot_npa, depot_ville, depot_rue)
                lat, lng = geocode_address(full_address)
                if lat and lng:
                    st.session_state.depot = {
                        'nom': depot_nom,
                        'rue': depot_rue,
                        'npa': depot_npa,
                        'ville': depot_ville,
                        'full_address': full_address,
                        'lat': lat,
                        'lng': lng,
                        'latlng': (lat, lng),
                        'heure_depart': depot_heure
                    }
                    st.session_state.step = 2
                    st.rerun()
                else:
                    st.error("Impossible de géocoder l'adresse du dépôt. Veuillez vérifier l'adresse.")
            else:
                st.error("Veuillez remplir tous les champs du dépôt.")

def show_client_form():
    st.header("📦 2. Vos Clients / Points de Passage")
    st.write("Ajoutez vos arrêts. Le type 'Livraison' sera priorisé à l'aller, 'Ramasse' au retour.")
    
    # Affichage du dépôt et de l'heure de départ pour rappel
    if st.session_state.depot:
        st.info(f"**Dépôt :** {st.session_state.depot['nom']} ({st.session_state.depot['full_address']})<br>**Heure de départ :** {st.session_state.depot['heure_depart'].strftime('%H:%M')}", unsafe_allow_html=True)

    with st.form("client_form", clear_on_submit=True):
        client_nom = st.text_input("Nom du client / Point de passage")
        client_rue = st.text_input("Rue et numéro")
        client_npa = st.text_input("NPA (code postal)")
        client_ville = st.text_input("Ville")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            client_type = st.selectbox("Type de mission", ["Livraison", "Ramasse"], index=0)
        with col2:
            client_dur = st.number_input("Durée estimée (min)", min_value=1, value=15)
        with col3:
            # Nouvelle option pour les ramasses
            consider_as_delivery_for_calc = False
            if client_type == "Ramasse":
                consider_as_delivery_for_calc = st.checkbox("Considérer comme Livraison (pour calcul)", help="Force ce point à être traité durant la phase 'aller' par l'algorithme, même si c'est une ramasse.")
        
        st.subheader("Contraintes (Optionnel)")
        col4, col5 = st.columns(2)
        with col4:
            heure_debut_fenetre = st.time_input("Début fenêtre horaire", None)
        with col5:
            heure_fin_fenetre = st.time_input("Fin fenêtre horaire", None)
            
        # Champ pour force l'ordre (option avancée)
        order_priority = st.number_input("Priorité d'ordre manuelle (plus bas = plus tôt)", min_value=0, value=999, step=1, format="%d")
        
        if st.form_submit_button("Ajouter l'arrêt"):
            if client_nom and client_rue and client_npa and client_ville:
                
                # Convertir les heures en format utilisable
                h_debut = heure_debut_fenetre if heure_debut_fenetre != datetime.now().time() else None
                h_fin = heure_fin_fenetre if heure_fin_fenetre != datetime.now().time() else None

                st.session_state.clients.append({
                    'nom': client_nom,
                    'rue': client_rue,
                    'npa': client_npa,
                    'ville': client_ville,
                    'type': client_type,
                    'dur': client_dur,
                    'heure_debut_fenetre': h_debut,
                    'heure_fin_fenetre': h_fin,
                    'consider_as_delivery_for_calc': consider_as_delivery_for_calc,
                    'order_priority': order_priority
                })
            else:
                st.error("Veuillez remplir tous les champs obligatoires pour le client.")

    st.subheader("Liste des arrêts saisis :")
    if not st.session_state.clients:
        st.info("Aucun arrêt n'a encore été ajouté.")
    else:
        # Affichage des clients avec possibilité de suppression
        cols_display = st.columns([0.1, 0.3, 0.3, 0.1, 0.1, 0.1]) # Ajuster les largeurs si besoin
        cols_display[0].markdown("**#**")
        cols_display[1].markdown("**Client**")
        cols_display[2].markdown("**Adresse**")
        cols_display[3].markdown("**Type**")
        cols_display[4].markdown("**Durée**")
        cols_display[5].markdown("**Actions**")
        
        for i, client in enumerate(st.session_state.clients):
            cols_display = st.columns([0.1, 0.3, 0.3, 0.1, 0.1, 0.1])
            cols_display[0].text(str(i+1))
            cols_display[1].text(client['nom'])
            cols_display[2].text(f"{client['npa']} {client['ville']}, {client['rue']}")
            
            type_display = client['type']
            if client['type'] == 'Ramasse' and client.get('consider_as_delivery_for_calc'):
                type_display += " (Calc. Liv.)"
                
            cols_display[3].text(type_display)
            cols_display[4].text(f"{client['dur']} min")
            
            # Bouton de suppression
            if cols_display[5].button("❌", key=f"del_{i}"):
                del st.session_state.clients[i]
                st.rerun() # Rafraîchir pour mettre à jour la liste

    st.markdown("---")
    
    col_mode, col_wait = st.columns(2)
    with col_mode:
        st.session_state.optimization_mode = st.radio(
            "Mode d'optimisation",
            ("Driving (Google Maps)", "Logique Chauffeur (Aller/Retour)"),
            index=1 if 'optimization_mode' not in st.session_state or st.session_state.optimization_mode == "Logique Chauffeur (Aller/Retour)" else 0,
            horizontal=True
        )
        # Mapping pour le backend
        if st.session_state.optimization_mode == "Driving (Google Maps)":
            backend_mode = "driving"
        else:
            backend_mode = "logic_chauffeur"

    with col_wait:
        st.session_state.max_wait_time = st.slider("Temps d'attente maximal toléré (min)", min_value=0, max_value=30, value=st.session_state.max_wait_time, step=5)

    if st.button("🚀 Calculer la tournée optimisée"):
        if st.session_state.depot and st.session_state.clients:
            st.session_state.step = 3
            st.rerun()
        else:
            st.warning("Veuillez définir votre dépôt et ajouter au moins un client pour calculer la tournée.")

def show_optimization_results():
    st.header("🚀 Tournée Optimisée")

    if not st.session_state.depot or not st.session_state.clients:
        st.warning("Données de dépôt ou de clients manquantes. Retour à l'étape précédente.")
        st.session_state.step = 1
        st.rerun()

    # Définir le mode d'optimisation
    mode = "driving" if st.session_state.optimization_mode == "Driving (Google Maps)" else "logic_chauffeur"

    # Préparer l'heure de départ au format datetime
    depot_info = st.session_state.depot
    current_date = datetime.now().date()
    departure_time_dt = datetime.combine(current_date, depot_info['heure_depart'])

    # Calcul de l'optimisation
    ordered_clients, total_distance_m, total_duration_secs, total_wait_time_secs = calculate_route_optimization(
        st.session_state.clients,
        st.session_state.depot,
        mode=mode,
        departure_time_dt=departure_time_dt
    )

    # Affichage des résultats globaux
    col_summary1, col_summary2, col_summary3 = st.columns(3)
    col_summary1.metric("Distance totale", f"{total_distance_m / 1000:.1f} km")
    
    total_duration_mins = total_duration_secs / 60
    hours = int(total_duration_mins // 60)
    minutes = int(total_duration_mins % 60)
    col_summary2.metric("Durée totale estimée", f"{hours}h{minutes:02d}")
    
    col_summary3.metric("Temps d'attente total", f"{total_wait_time_secs / 60:.0f} min")
    
    st.markdown("---")

    # --- Affichage de la carte ---
    st.subheader("🗺️ Carte de la tournée")
    m_final = folium.Map(location=st.session_state.depot['latlng'], zoom_start=12)
    
    # Marqueur pour le dépôt
    folium.Marker(
        st.session_state.depot['latlng'],
        popup=f"<b>Dépôt:</b> {st.session_state.depot['nom']}<br>{st.session_state.depot['full_address']}",
        icon=folium.Icon(color="green", icon="home")
    ).add_to(m_final)

    # Si on a des données ordonnées pour construire les segments
    if ordered_clients:
        # Calculer les coordonnées pour chaque segment
        path_coords = [st.session_state.depot['latlng']]
        
        for i, client in enumerate(ordered_clients):
            start_location = path_coords[-1] # Dernière position enregistrée
            end_location = (client['lat'], client['lng'])

            # Récupérer le chemin réel entre le point de départ et d'arrivée pour ce segment
            # Utilisation de l'API Directions pour avoir le polyline et les détails du segment
            try:
                # Il faut spécifier departure_time pour le premier segment, puis on le met à None pour les suivants car le temps réel est déjà calculé
                departure_time_arg = int(departure_time_dt.timestamp()) if i == 0 else None
                
                # IMPORTANT: Si le mode est "logic_chauffeur", on a déjà calculé les legs dans `calculate_route_optimization`
                # Il faudrait stocker ces legs pour les réutiliser ici, sinon on fait des appels API redondants
                
                # Pour l'instant, on refait un appel API pour simplifier le code.
                # Si la performance est un problème, il faut stocker les `res_leg` retournés par `calculate_route_optimization`
                
                res_leg = gmaps.directions(
                    f"{start_location[0]},{start_location[1]}",
                    f"{end_location[0]},{end_location[1]}",
                    mode="driving", # Toujours driving pour le polyline
                    departure_time=departure_time_arg # Utiliser le temps de départ si c'est le premier segment
                )
                
                if res_leg:
                    leg = res_leg[0]['legs'][0]
                    # Ajouter les coordonnées du segment au chemin global
                    points = polyline.decode(res_leg[0]['overview_polyline']['points'])
                    path_coords.extend(points) # Ajoute les points du segment

                    # Affichage du marqueur et du popup pour le client
                    folium.Marker(
                        end_location,
                        popup=folium.Popup(
                            f"""
                            <b>{client['nom']}</b><br>
                            {client['npa']} {client['ville']}, {client['rue']}<br>
                            <hr style='margin: 5px 0;'>
                            Type: {client['type']}<br>
                            Durée: {client['dur']} min<br>
                            <span class="{client.get('status_class', '')}">{client.get('status', '')}</span><br>
                            Arr: {client.get('heure_arrivee_estimee', 'N/A')}<br>
                            Dep: {client.get('heure_depart_estimee', 'N/A')}<br>
                            Trajet: {leg['distance']['text']} ({leg['duration']['text']})
                            """,
                            max_width=300
                        ),
                        icon=folium.Icon(color="blue") # La couleur peut être changée selon le type (Livraison/Ramasse)
                    ).add_to(m_final)
                    
                    # On met à jour `path_coords` avec la localisation du client actuel
                    path_coords.append(end_location)
            
            except Exception as e:
                st.error(f"Erreur lors du tracé du segment de la carte : {e}")

        # Tracer le polyline de la tournée
        if len(path_coords) > 1:
            folium.PolyLine(path_coords, color="blue", weight=5, opacity=0.7).add_to(m_final)
            
        folium_static(m_final, width=1000)
    
    else:
        st.warning("Aucun itinéraire n'a pu être généré.")

    # --- Affichage détaillé des arrêts ---
    st.subheader("📋 Détail des arrêts")
    if not ordered_clients:
        st.info("Aucun arrêt à afficher.")
    else:
        for i, client in enumerate(ordered_clients):
            full_address = format_address(client['npa'], client['ville'], client['rue'])
            
            # Préparation des informations de contraintes à afficher
            constraints_html = ""
            if client.get('heure_debut_fenetre') and client.get('heure_fin_fenetre'):
                constraints_html += f"<p>Fenêtre Horaire: {client['heure_debut_fenetre'].strftime('%H:%M')} - {client['heure_fin_fenetre'].strftime('%H:%M')}</p>"
            
            constraints_html += f"<p>Durée estimée: {client['dur']} min</p>"
            
            if client.get('status'):
                constraints_html += f"<p class='{client.get('status_class', '')}'>Statut: {client['status']}</p>"
            
            if client.get('temps_attente_sec', 0) > 0:
                 constraints_html += f"<p>Temps d'attente: {client['temps_attente_sec']/60:.0f} min</p>"
            
            if client.get('temps_trajet_secs'):
                secs = client['temps_trajet_secs']
                mins = secs // 60
                secs_rem = secs % 60
                constraints_html += f"<p>Trajet (vers ce point): {mins} min {secs_rem} s</p>"

            client_display_type = client['type']
            if client.get('consider_as_delivery_for_calc'):
                client_display_type += " (Calc. Liv.)"

            # Affichage de la carte pour chaque client (simplifié, juste pour la visualisation rapide)
            # On peut retirer ceci si ça ralentit trop le rendu
            client_map_col, client_info_col = st.columns([0.3, 0.7])
            
            with client_map_col:
                m_client = folium.Map(location=[client['lat'], client['lng']], zoom_start=15, height=150)
                folium.Marker([client['lat'], client['lng']], icon=folium.Icon(color="blue")).add_to(m_client)
                folium_static(m_client, width=300)

            with client_info_col:
                st.markdown(f"""
                <div class="client-card">
                    <b>{i+1}. {client['nom']}</b> 
                    <span style="font-size: 0.8em;">({client_display_type})</span>
                </div>
                <div class="address-box">
                    <p>{client['npa']} {client['ville']}, {client['rue']}</p>
                    {constraints_html}
                    <p>Arrivée estimée: {client.get('heure_arrivee_estimee', 'N/A')}</p>
                    <p>Départ estimé: {client.get('heure_depart_estimee', 'N/A')}</p>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("---")

    st.subheader("🏁 Retour au Dépôt (Optionnel)")
    st.write("Le temps total affiché n'inclut pas le trajet retour au dépôt. Vous pouvez le calculer si nécessaire.")

    if st.button("✏️ Modifier la tournée"):
        st.session_state.step = 2
        st.rerun()
    if st.button("🔄 Recommencer"):
        st.session_state.clients = []
        st.session_state.depot = None
        st.session_state.step = 1
        st.rerun()

# --- AFFICHAGE PRINCIPAL SELON L'ÉTAPE ---
if st.session_state.step == 1:
    show_depot_form()
elif st.session_state.step == 2:
    show_client_form()
elif st.session_state.step == 3:
    show_optimization_results()
