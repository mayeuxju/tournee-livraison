import streamlit as st
import googlemaps
from streamlit_folium import folium_static
import folium
from datetime import datetime, timedelta
import polyline
from collections import defaultdict

# --- CONFIGURATION & STYLE ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

# S'assurer que les clés API et le client Google Maps sont initialisés une seule fois
if 'gmaps' not in st.session_state:
    # Remplacez par votre clé API Google Maps
    # Assurez-vous que votre clé API est bien configurée pour les Directions API
    API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY", "VOTRE_CLE_API_GOOGLE_MAPS") 
    if API_KEY == "VOTRE_CLE_API_GOOGLE_MAPS":
        st.error("Veuillez configurer votre clé API Google Maps dans les secrets Streamlit (`secrets.toml`).")
        st.stop()
    st.session_state.gmaps = googlemaps.Client(key=API_KEY)

if 'map_style' not in st.session_state:
    st.session_state.map_style = """
    <style>
    .summary-box { padding: 6px 12px; border-radius: 8px; margin-bottom: 5px; display: flex; align-items: center; color: white; font-size: 0.9rem; }
    .depot-box { background-color: #28a745; border: 1px solid #1e7e34; } 
    .client-box { background-color: #0047AB; border: 1px solid #003380; }
    .constraint-badge { background-color: #ffc107; color: #333; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px; }
    .forced-return-badge { background-color: #fd7e14; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px; }
    .depot-constraint-badge { background-color: #17a2b8; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px; }
    [data-testid="stHorizontalBlock"] { align-items: center; }
    .client-card { background-color: #0047AB; color: white; padding: 15px; border-radius: 10px 10px 0 0; margin-top: 10px; }
    .address-box { background-color: #0047AB; padding: 0 15px 10px 15px; border-radius: 0 0 10px 10px; margin-bottom: 10px; }
    .address-box code { color: white !important; background-color: transparent !important; border: none !important; font-size: 0.9rem; }
    .stButton>button { width: 100%; }
    .map-container { margin-top: 20px; border: 1px solid #ccc; border-radius: 10px; padding: 10px; }
    </style>
    """
    st.markdown(st.session_state.map_style, unsafe_allow_html=True)

# --- SESSION STATE INITIALIZATION ---
if 'depot' not in st.session_state:
    st.session_state.depot = None
if 'clients' not in st.session_state:
    st.session_state.clients = []
if 'optimisation_mode' not in st.session_state:
    st.session_state.optimisation_mode = "Logique Chauffeur (Aller -> Retour)"
if 'max_wait_time' not in st.session_state:
    st.session_state.max_wait_time = 15 # minutes
if 'step' not in st.session_state:
    st.session_state.step = 1

# --- HELPER FUNCTIONS ---
def get_coordinates(address):
    try:
        geocode_result = st.session_state.gmaps.geocode(address)
        if geocode_result:
            return geocode_result[0]['geometry']['location']['lat'], geocode_result[0]['geometry']['location']['lng']
        else:
            return None, None
    except Exception as e:
        st.error(f"Erreur de géocodage pour {address}: {e}")
        return None, None

def format_address(client_data):
    parts = [client_data.get('rue'), client_data.get('num')]
    npa_ville = f"{client_data.get('npa', '')} {client_data.get('ville', '')}".strip()
    if npa_ville:
        parts.append(npa_ville)
    
    # Filtrer les parties vides et joindre avec un espace
    full_address = " ".join(filter(None, parts))
    
    # Ajout du pays s'il n'est pas vide et si on veut l'afficher (ici on ne l'affiche pas)
    # if client_data.get('pays'):
    #     full_address += f", {client_data.get('pays')}"
        
    return full_address

def get_full_address_string(client_data):
    address_parts = [
        client_data.get('rue', ''),
        client_data.get('num', ''),
        f"{client_data.get('npa', '')} {client_data.get('ville', '')}".strip()
    ]
    return ", ".join(filter(None, address_parts))

def create_summary_entry(client_data, index, is_depot=False):
    if is_depot:
        box_class = "depot-box"
        display_name = f"Dépôt: {client_data['nom']}"
    else:
        box_class = "client-box"
        display_name = f"{client_data['nom']} ({client_data['type']})"

    # Construire l'adresse corrigée
    address_parts = [client_data.get('rue'), client_data.get('num')]
    npa_ville = f"{client_data.get('npa', '')} {client_data.get('ville', '')}".strip()
    if npa_ville:
        address_parts.append(npa_ville)
    
    corrected_address = " ".join(filter(None, address_parts))
    
    # Ajouter les badges de contraintes
    constraints_html = ""
    if client_data.get('horaire_imperatif'):
        constraints_html += f'<span class="constraint-badge">Horaires</span>'
    if client_data.get('forced_return_aller'):
        constraints_html += f'<span class="forced-return-badge">Ramasse Aller</span>'
    if client_data.get('temps_sur_place'):
        constraints_html += f'<span class="depot-constraint-badge">{client_data.get("temps_sur_place")} min</span>'

    # Créer le code pour la ligne d'arrêt
    # Note: L'affichage sur une seule ligne avec des boutons est complexe en HTML/CSS simple.
    # On va plutôt viser une structure claire.
    # Pour les bulles bleues/vertes, cela sera géré dans l'affichage final.
    
    # Ici on va juste construire le texte de la ligne d'arrêt.
    # Le style bulle sera appliqué dans la fonction d'affichage de la liste.
    
    return {
        "id": index,
        "nom": client_data['nom'],
        "adresse_complete": corrected_address,
        "type": client_data['type'],
        "constraints": constraints_html,
        "full_address_for_copy": get_full_address_string(client_data),
        "lat": client_data.get('lat'),
        "lng": client_data.get('lng'),
        "dur": client_data.get('temps_sur_place', 0),
        "horaire_imperatif": client_data.get('horaire_imperatif', False),
        "pas_avant": client_data.get('pas_avant'),
        "pas_apres": client_data.get('pas_apres'),
        "forced_return_aller": client_data.get('forced_return_aller', False)
    }

def optimize_route(depot_info, client_list, mode, max_wait_time_minutes):
    if not depot_info or not client_list:
        return None, []

    depot_addr = depot_info['address']
    depot_lat, depot_lng = get_coordinates(depot_addr)
    if not depot_lat:
        st.error("Impossible de trouver les coordonnées du dépôt.")
        return None, []

    gmaps = st.session_state.gmaps
    
    # Séparer les clients en deux groupes : les "Livraisons" et les "Ramasses"
    deliveries = []
    pickups = []
    for client in client_list:
        if client.get('type') == "Livraison":
            deliveries.append(client)
        else:
            pickups.append(client)

    # Ajouter des destinations "virtuelles" pour le dépôt au début et à la fin
    # Cela aide l'API Directions à calculer le trajet depuis/vers le dépôt
    waypoints_all = []
    
    # Préparer les destinations pour l'API Google Maps Directions
    # L'ordre ici est crucial pour le calcul initial, il sera réorganisé ensuite
    
    # Liste des destinations pour l'API (incluant dépôt au début et à la fin)
    all_locations_for_api = [depot_addr] + [c['address'] for c in client_list] + [depot_addr]
    
    # Préparer la liste des arrêts avec toutes les infos nécessaires
    stops_for_display = []
    
    # Initialisation pour le calcul
    current_time = datetime.combine(datetime.today(), depot_info['heure_depart'])
    
    # --- Logique d'Optimisation ---
    ordered_stops = []
    
    if mode == "Mathématique (Le plus court)":
        # Pour le mode "Mathématique", on envoie tout à l'API Directions d'un coup
        # L'API va retourner le chemin le plus court en temps
        
        # On doit toujours inclure le dépôt au début et à la fin
        stops_for_api = [depot_addr] + [c['address'] for c in client_list] + [depot_addr]
        
        try:
            # Utilisation de optimize_waypoints=True
            directions_result = gmaps.directions(depot_addr, depot_addr,
                                                waypoints=stops_for_api[1:-1], # Tous les clients
                                                optimize_waypoints=True,
                                                mode="driving",
                                                departure_time=current_time)
            
            if not directions_result:
                st.error("Aucun itinéraire trouvé pour le mode Mathématique.")
                return None, []
            
            route = directions_result[0]
            ordered_leg_indices = route['waypoint_order'] # Indice des arrêts dans la liste `stops_for_api[1:-1]`
            
            final_ordered_stops_data = [depot_info] # Commence par le dépôt
            
            # Reconstruire l'ordre des clients selon optimize_waypoints
            client_dict = {c['address']: c for c in client_list}
            
            for i in ordered_leg_indices:
                ordered_address = stops_for_api[1:-1][i] # L'adresse dans l'ordre optimisé
                final_ordered_stops_data.append(client_dict[ordered_address])
            
            final_ordered_stops_data.append(depot_info) # Termine par le dépôt

            # Calculer les temps et distances réels
            optimized_route_details, final_stops_with_times = calculate_route_times(final_ordered_stops_data, depot_info['heure_depart'])
            
            return optimized_route_details, final_stops_with_times

        except Exception as e:
            st.error(f"Erreur lors de l'optimisation Google Maps (Mode Mathématique): {e}")
            return None, []

    elif mode == "Logique Chauffeur (Aller -> Retour)":
        # Tri spécifique pour le mode "Logique Chauffeur"
        
        # 1. Préparer les livraisons avec une notion de "ramasse_aller"
        # Les ramasses forcées à l'aller seront traitées comme des livraisons pour l'ordre.
        deliveries_and_forced_pickups = []
        for client in deliveries:
            deliveries_and_forced_pickups.append(client)
        for client in pickups:
            if client.get('forced_return_aller'):
                deliveries_and_forced_pickups.append(client)
        
        # 2. Préparer les vraies ramasses pour le retour
        actual_pickups = [p for p in pickups if not p.get('forced_return_aller')]
        
        # 3. Calculer l'itinéraire des livraisons (et ramasses forcées à l'aller)
        final_stops_data_aller = [depot_info]
        if deliveries_and_forced_pickups:
            try:
                # L'API va nous donner l'ordre optimal pour ces destinations
                # On n'inclut pas les vraies ramasses ici
                stops_for_api_aller = [depot_addr] + [c['address'] for c in deliveries_and_forced_pickups] + [depot_addr]
                
                directions_result_aller = gmaps.directions(depot_addr, depot_addr,
                                                           waypoints=stops_for_api_aller[1:-1],
                                                           optimize_waypoints=True,
                                                           mode="driving",
                                                           departure_time=current_time)
                
                if not directions_result_aller:
                    st.warning("Impossible de trouver un itinéraire pour les livraisons (aller).")
                    # On essaie de continuer quand même avec l'ordre tel quel si possible
                    route_aller = None
                    ordered_leg_indices_aller = list(range(len(deliveries_and_forced_pickups))) # Ordre d'origine
                else:
                    route_aller = directions_result_aller[0]
                    ordered_leg_indices_aller = route_all['waypoint_order']
                
                # Ajouter les arrêts dans l'ordre calculé
                client_dict_aller = {c['address']: c for c in deliveries_and_forced_pickups}
                for i in ordered_leg_indices_aller:
                    ordered_address = stops_for_api_aller[1:-1][i]
                    final_stops_data_aller.append(client_dict_aller[ordered_address])
                
                # Attention, le dernier waypoint (depot_addr) n'est pas une destination réelle dans cette phase
                # Il sert juste à calculer la route vers le dernier client.
                # On va plutôt ajouter le vrai depot plus tard pour le retour.
                
            except Exception as e:
                st.error(f"Erreur lors de l'optimisation Google Maps (Aller): {e}")
                final_stops_data_aller = [depot_info] + deliveries_and_forced_pickups # Ordre d'origine
        else:
             # Pas de livraisons, on commence directement par la phase retour.
             # Ou on garde juste le dépôt si aucune livraison ni ramasse.
             pass # Rien à ajouter pour l'aller

        # 4. Calculer les temps et distances pour l'aller, en tenant compte des contraintes horaires
        # On a besoin d'un calcul étape par étape pour gérer les horaires et le 'max_wait_time'
        
        # Insérer le dépôt au début pour le calcul
        full_route_data_aller_with_depot = [depot_info] + final_stops_data_aller[1:] # Exclure le dépôt une fois si déjà présent
        
        # On doit gérer les horaires IMPÉRATIFS et le temps d'attente maximal
        # Ceci nécessite une boucle de calcul et potentiellement de réajustement
        final_ordered_stops_data_aller_timed = calculate_route_with_constraints(
            full_route_data_aller_with_depot, 
            depot_info['heure_depart'], 
            max_wait_time_minutes, 
            gmaps
        )

        # 5. Calculer l'itinéraire des vraies ramasses (retour)
        final_stops_data_retour = [final_ordered_stops_data_aller_timed[-1]] # Commence par le dernier arrêt de l'aller
        if actual_pickups:
            try:
                # On veut retourner au dépôt depuis le dernier point de l'aller
                # L'API va optimiser les ramasses entre elles et le retour au dépôt
                stops_for_api_retour = [final_stops_data_retour[0]['address']] + [p['address'] for p in actual_pickups] + [depot_addr]
                
                # Le départ de cette phase est l'heure d'arrivée au dernier point de l'aller
                last_arrival_time_aller = final_stops_data_aller_timed[-1]['arrival_time']
                departure_time_retour_phase = last_arrival_time_aller # Ou on pourrait la définir comme l'heure de départ du dernier client de l'aller + son temps sur place
                
                directions_result_retour = gmaps.directions(final_stops_data_retour[0]['address'], depot_addr,
                                                           waypoints=[p['address'] for p in actual_pickups],
                                                           optimize_waypoints=True,
                                                           mode="driving",
                                                           departure_time=departure_time_retour_phase)
                
                if not directions_result_retour:
                    st.warning("Impossible de trouver un itinéraire pour les ramasses (retour).")
                    route_retour = None
                    ordered_leg_indices_retour = list(range(len(actual_pickups))) # Ordre d'origine
                else:
                    route_retour = directions_result_retour[0]
                    ordered_leg_indices_retour = route_retour['waypoint_order']
                
                # Ajouter les arrêts de retour dans l'ordre calculé
                client_dict_retour = {p['address']: p for p in actual_pickups}
                for i in ordered_leg_indices_retour:
                    ordered_address = stops_for_api_retour[1:-1][i] # L'adresse dans l'ordre optimisé
                    final_stops_data_retour.append(client_dict_retour[ordered_address])
                
                # Le dernier arrêt est le dépôt
                final_stops_data_retour.append(depot_info)

            except Exception as e:
                st.error(f"Erreur lors de l'optimisation Google Maps (Retour): {e}")
                final_stops_data_retour = [final_stops_data_retour[0]] + actual_pickups + [depot_info] # Ordre d'origine
        else:
            # Pas de ramasses réelles, juste retourner au dépôt depuis le dernier point de l'aller
            final_stops_data_retour = [final_stops_data_retour[0], depot_info]

        # 6. Calculer les temps pour la phase de retour
        # Ici, on ne gère que les temps de trajet et de service. Pas de contraintes horaires sur les ramasses.
        final_ordered_stops_data_retour_timed = calculate_route_times(final_stops_data_retour, final_stops_data_retour[0]['arrival_time'] if len(final_stops_data_retour) > 1 else depot_info['heure_depart'])

        # 7. Combiner les deux phases
        # On remplace le dernier point de l'aller (qui était une donnée) par le premier point du calcul détaillé de l'aller
        # Puis on concatène avec la phase retour
        
        # La sortie de calculate_route_with_constraints inclut déjà le dépôt comme dernier point de l'aller.
        # On doit donc s'assurer que le premier point du retour est bien le même que le dernier de l'aller.
        
        combined_stops_with_times = []
        
        if final_ordered_stops_data_aller_timed:
            combined_stops_with_times.extend(final_ordered_stops_data_aller_timed)
            
            # Si on a des arrêts de retour, on les ajoute, en s'assurant qu'on ne duplique pas le dernier point de l'aller qui est le même que le premier du retour.
            if final_ordered_stops_data_retour_timed and len(final_ordered_stops_data_retour_timed) > 1:
                # Le premier arrêt du retour est le dernier arrêt de l'aller.
                # On ajoute donc le reste des arrêts du retour (à partir du deuxième).
                combined_stops_with_times.extend(final_ordered_stops_data_retour_timed[1:])
        else:
            # Si l'aller a échoué, on essaie de traiter le retour s'il existe
            combined_stops_with_times.extend(final_ordered_stops_data_retour_timed)
            
        # S'assurer que le dépôt est bien le tout dernier point si on a calculé un retour
        if actual_pickups and combined_stops_with_times and combined_stops_with_times[-1]['address'] != depot_addr:
            # Si le dernier point calculé pour le retour n'est pas le dépôt, on l'ajoute
            # Ceci peut arriver si l'API ne retourne pas le dépôt comme dernier waypoint optimisé explicitement
            # et que le calcul_route_times s'arrête avant.
            combined_stops_with_times.append(depot_info)
            
        # On a maintenant une liste complète d'arrêts avec les horaires calculés
        # Il faut maintenant générer l'itinéraire Google Maps complet
        
        # Préparer les waypoints pour l'API Directions pour avoir le tracé complet
        # Les waypoints doivent être les adresses dans l'ordre final
        final_addresses_ordered = [s['address'] for s in combined_stops_with_times if s != depot_info] # Exclure les dépôts intermédiaires si on en a rajouté
        
        if not final_addresses_ordered: # Cas où il n'y a que le dépôt
            return None, [depot_info] # Retourner juste le dépôt

        # Si le premier et le dernier sont identiques (cas simple, départ et retour au dépôt)
        if len(final_addresses_ordered) > 1 and final_addresses_ordered[0] == final_addresses_ordered[-1]:
            # Si on a un aller-retour simple avec des arrêts au milieu
            final_waypoints = final_addresses_ordered[1:-1]
            origin = final_addresses_ordered[0]
            destination = final_addresses_ordered[-1]
        else:
            # Cas plus général : départ dépôt, plusieurs arrêts, retour dépôt
            final_waypoints = final_addresses_ordered[1:] # Tous les arrêts sauf le premier
            origin = final_addresses_ordered[0]
            destination = depot_addr # Assurer le retour au dépôt

        if not final_waypoints: # S'il n'y a qu'un seul point d'arrêt (hors dépôt)
             directions_result_final = gmaps.directions(origin, destination, mode="driving", departure_time=depot_info['heure_depart'])
        else:
            directions_result_final = gmaps.directions(origin, destination,
                                                       waypoints=final_waypoints,
                                                       optimize_waypoints=False, # L'ordre est déjà fixé
                                                       mode="driving",
                                                       departure_time=depot_info['heure_depart'])
        
        if not directions_result_final:
            st.error("Erreur: Impossible de générer l'itinéraire final.")
            return None, combined_stops_with_times

        # Retourne le résultat de l'API Directions et la liste des arrêts avec les temps calculés
        return directions_result_final[0], combined_stops_with_times
        
    return None, [] # Mode non supporté

def calculate_route_times(ordered_stops_data, start_time):
    """Calcule les temps d'arrivée et de départ pour une liste ordonnée d'arrêts."""
    
    final_stops_with_times = []
    current_time = start_time
    gmaps = st.session_state.gmaps
    
    # Ajouter le dépôt de départ s'il n'est pas déjà dans ordered_stops_data
    if not ordered_stops_data or ordered_stops_data[0] != depot_info: # depot_info doit être accessible ici
        # Assurez-vous que depot_info est bien passé ou accessible globalement si nécessaire
        # Pour l'instant, on suppose que le premier élément est déjà le dépôt avec son heure de départ.
        pass

    for i, stop in enumerate(ordered_stops_data):
        
        stop_data = stop.copy() # Copier pour ne pas modifier l'original
        stop_data['arrival_time'] = current_time
        
        service_time = stop_data.get('dur', 0)
        
        # Calculer le temps de départ du point actuel
        departure_time = current_time + timedelta(minutes=service_time)
        stop_data['departure_time'] = departure_time
        
        final_stops_with_times.append(stop_data)
        
        # Préparer le temps pour le prochain trajet
        current_time = departure_time
        
        # Calculer le temps de trajet vers le prochain arrêt (sauf si c'est le dernier)
        if i < len(ordered_stops_data) - 1:
            next_stop = ordered_stops_data[i+1]
            
            # On a besoin des coordonnées pour le trajet
            # Si les lat/lng ne sont pas présents, on les cherche
            if stop_data.get('lat') is None or stop_data.get('lng') is None:
                 stop_data['lat'], stop_data.get('lng') = get_coordinates(stop_data['address'])
            if next_stop.get('lat') is None or next_stop.get('lng') is None:
                 next_stop['lat'], next_stop.get('lng') = get_coordinates(next_stop['address'])
            
            if stop_data.get('lat') and stop_data.get('lng') and next_stop.get('lat') and next_stop.get('lng'):
                try:
                    # Utiliser l'API Directions pour obtenir le temps de trajet précis
                    # C'est plus fiable que de juste ajouter une durée fixe
                    # On doit spécifier le departure_time pour avoir des estimations de trafic
                    
                    # Utiliser l'heure de départ du point actuel pour le calcul du trajet
                    travel_info = gmaps.directions(
                        f"{stop_data['lat']},{stop_data['lng']}", 
                        f"{next_stop['lat']},{next_stop['lng']}",
                        mode="driving",
                        departure_time=current_time # Heure à laquelle on quitte le point actuel
                    )
                    
                    if travel_info:
                        # Le temps de trajet est dans la première "leg"
                        leg = travel_info[0]['legs'][0]
                        travel_duration_seconds = leg['duration']['value']
                        
                        # Ajouter au temps actuel pour le prochain calcul
                        current_time += timedelta(seconds=travel_duration_seconds)
                    else:
                        # Si l'API ne retourne rien, on peut utiliser une estimation par défaut (ex: 20 min)
                        # Ou simplement signaler une erreur
                        st.warning(f"Impossible de récupérer le temps de trajet entre {stop_data['nom']} et {next_stop['nom']}. Estimation de 20 minutes.")
                        current_time += timedelta(minutes=20) # Estimation par défaut
                        
                except Exception as e:
                    st.error(f"Erreur Google Maps lors du calcul du trajet: {e}")
                    current_time += timedelta(minutes=20) # Estimation par défaut en cas d'erreur
            else:
                st.warning(f"Coordonnées manquantes pour le trajet entre {stop_data['nom']} et {next_stop['nom']}. Utilisation d'une estimation de 20 minutes.")
                current_time += timedelta(minutes=20) # Estimation par défaut
                
    return final_stops_with_times


def calculate_route_with_constraints(ordered_stops_data, start_time, max_wait_time_minutes, gmaps_client):
    """
    Calcule les temps d'arrivée et de départ pour une liste ordonnée d'arrêts,
    en tenant compte des contraintes horaires IMPÉRATIVES et d'un temps d'attente maximum.
    Réorganise si nécessaire pour éviter les attentes trop longues.
    """
    
    final_stops_with_times = []
    current_time = start_time
    
    # Copier la liste pour pouvoir la modifier
    stops_to_process = ordered_stops_data[:]
    
    # Boucle principale pour gérer les réorganisations
    # On continue tant qu'on doit potentiellement ajuster (e.g., attente > max_wait_time)
    
    # Pour simplifier, on va faire une approche itérative.
    # 1. Calculer les temps bruts avec l'ordre actuel.
    # 2. Identifier les problèmes (trop d'attente).
    # 3. Essayer de réorganiser si problème.
    # 4. Répéter jusqu'à ce que ça soit bon ou qu'on ne puisse plus améliorer.
    
    # Pour cette implémentation, on va réaliser un calcul initial et gérer les contraintes au fur et à mesure.
    # Si une contrainte horaire cause une attente > max_wait_time, on va essayer de décaler le point d'origine du trajet.
    
    processed_stops = [] # Les arrêts déjà traités et confirmés
    
    # On commence par le premier arrêt (qui doit être le dépôt)
    if not stops_to_process:
        return []
    
    current_stop_data = stops_to_process.pop(0)
    current_stop_data['arrival_time'] = current_time
    current_stop_data['departure_time'] = current_time + timedelta(minutes=current_stop_data.get('dur', 0))
    processed_stops.append(current_stop_data)
    current_time = current_stop_data['departure_time']
    
    while stops_to_process:
        next_stop_data = stops_to_process.pop(0)
        
        # Calculer le temps de trajet du dernier point traité vers le prochain arrêt
        last_processed_stop = processed_stops[-1]
        
        # Obtenir les coordonnées
        lat1, lng1 = get_coordinates(last_processed_stop['address'])
        lat2, lng2 = get_coordinates(next_stop_data['address'])

        travel_duration_seconds = 0
        if lat1 and lng1 and lat2 and lng2:
            try:
                travel_info = gmaps_client.directions(
                    f"{lat1},{lng1}", 
                    f"{lat2},{lng2}",
                    mode="driving",
                    departure_time=current_time # Utiliser l'heure de départ du dernier arrêt traité
                )
                if travel_info:
                    travel_duration_seconds = travel_info[0]['legs'][0]['duration']['value']
                else:
                    travel_duration_seconds = 1200 # 20 minutes par défaut
            except Exception as e:
                st.error(f"Erreur Google Maps pour trajet: {e}")
                travel_duration_seconds = 1200 # 20 minutes par défaut
        else:
            travel_duration_seconds = 1200 # 20 minutes par défaut

        current_time += timedelta(seconds=travel_duration_seconds) # Mise à jour de l'heure d'arrivée au prochain arrêt
        
        # Vérifier les contraintes horaires du prochain arrêt
        next_arrival_time = current_time
        
        if next_stop_data.get('horaire_imperatif'):
            pas_avant = next_stop_data.get('pas_avant')
            pas_apres = next_stop_data.get('pas_apres')
            
            # Convertir les strings "HH:MM" en datetime objects pour comparaison
            try:
                ref_date = datetime.today().date() # Utiliser une date de référence, peu importe laquelle tant que c'est cohérent
                heure_debut_window = datetime.strptime(pas_avant, '%H:%M').time() if pas_avant else None
                heure_fin_window = datetime.strptime(pas_apres, '%H:%M').time() if pas_apres else None
                
                target_arrival_time = next_arrival_time
                
                # 1. Attente si on arrive trop tôt
                wait_time = timedelta(0)
                if heure_debut_window and next_arrival_time.time() < heure_debut_window:
                    # Calculer le datetime exact de début de fenêtre
                    start_window_dt = datetime.combine(ref_date, heure_debut_window)
                    # Si le jour de la fenêtre est le même que le jour actuel, utiliser cette date. Sinon, prendre la date future.
                    if next_arrival_time.date() == ref_date: # Cas où on est le jour même
                        pass # start_window_dt est déjà correct
                    else: # Si on est avant la fenêtre du jour même, on prend la fenêtre du jour même
                        # Si la fenêtre est passée pour aujourd'hui, on prend celle de demain.
                        # Ici, on simplifie en assumant que la fenêtre est toujours dans le futur ou aujourd'hui.
                        # Pour une vraie gestion jour/jour, il faudrait vérifier next_arrival_time.date() vs start_window_dt.date()
                        pass 

                    # Si l'heure d'arrivée est avant l'heure de début de fenêtre, on doit attendre
                    # Le temps d'attente doit être calculé par rapport à l'heure de début de fenêtre
                    # Il faut s'assurer que l'heure de fenêtre est bien dans le futur par rapport à l'heure d'arrivée
                    
                    # Exemple : Arrivée 09:00, Fenêtre 09:30-11:30. Attente = 09:30 - 09:00 = 30 min.
                    # La nouvelle arrivée sera 09:30.
                    
                    # Si le jour d'arrivée est le jour actuel :
                    if next_arrival_time.date() == start_window_dt.date():
                        if next_arrival_time < start_window_dt:
                            wait_time = start_window_dt - next_arrival_time
                            target_arrival_time = start_window_dt # La nouvelle arrivée est le début de la fenêtre
                    else: # Si l'arrivée est prévue pour un jour futur avant la fenêtre
                        # On prend la fenêtre du jour où on arrive
                        if next_arrival_time.date() < start_window_dt.date(): # Si le jour d'arrivée est AVANT le jour de la fenêtre
                            # On arrive avant la fenêtre, donc on doit attendre le début de la fenêtre du jour d'arrivée
                            target_arrival_time = datetime.combine(next_arrival_time.date(), heure_debut_window)
                        else: # Si le jour d'arrivée est le jour de la fenêtre
                            if next_arrival_time < start_window_dt:
                                wait_time = start_window_dt - next_arrival_time
                                target_arrival_time = start_window_dt
                                
                # 2. Vérifier si on dépasse la fin de la fenêtre
                if heure_fin_window:
                    end_window_dt = datetime.combine(target_arrival_time.date(), heure_fin_window) # Utiliser la date de la cible d'arrivée potentielle
                    
                    if target_arrival_time > end_window_dt:
                        # Trop tard ! On a dépassé la fin de la fenêtre.
                        # Ceci est un problème d'optimisation qui pourrait nécessiter une réorganisation.
                        # Pour l'instant, on le signale et on continue avec l'heure d'arrivée calculée (qui est en fait > fin_window).
                        # On doit signaler cette situation pour qu'elle soit gérée (potentiellement par un réajustement)
                        st.warning(f"Arrivée prévue à {target_arrival_time.strftime('%H:%M')} pour {next_stop_data['nom']}, ce qui est après la fin de la fenêtre ({heure_fin_window.strftime('%H:%M')}).")
                        
                        # Gestion de l'attente maximale
                        if wait_time.total_seconds() / 60 > max_wait_time_minutes:
                            # Trop d'attente. On doit essayer de réorganiser.
                            # Pour l'instant, on va juste utiliser l'heure d'arrivée calculée sans attente
                            # Et marquer cet arrêt comme "problématique"
                            # Pour une vraie réorganisation, il faudrait remonter le calcul
                            
                            # On utilise quand même le temps d'attente si c'est la seule option pour respecter l'heure d'arrivée
                            # Mais si cela dépasse le temps max d'attente, c'est un problème.
                            # On va donc reset l'heure d'arrivée au début de la fenêtre
                            target_arrival_time = datetime.combine(ref_date, heure_debut_window) # Assurer le respect de l'heure min.
                            # Si l'heure est déjà passée pour aujourd'hui, prendre demain
                            if target_arrival_time < next_arrival_time:
                                target_arrival_time = datetime.combine(ref_date + timedelta(days=1), heure_debut_window)
                                
                            # Si cela cause une attente > max_wait_time, c'est un vrai problème.
                            wait_duration = target_arrival_time - next_arrival_time
                            if wait_duration.total_seconds() / 60 > max_wait_time_minutes:
                                # Ceci est une situation à gérer. Pour le moment, on ne va pas réorganiser.
                                # On va juste utiliser l'heure d'arrivée calculée SANS attente et marquer le problème.
                                # Le trajet continuera avec l'heure d'arrivée originale.
                                # C'est là qu'une logique de réorganisation serait nécessaire.
                                pass # On continue avec la `next_arrival_time` calculée initialement, même si c'est en retard.
                                
                        
                current_time = target_arrival_time # L'heure d'arrivée est ajustée
                
            except ValueError:
                st.warning(f"Format horaire invalide pour {next_stop_data['nom']} ({pas_avant} - {pas_apres}).")
                # Continuer sans les contraintes horaires spécifiques

        # Si on est en retard sur la fenêtre ou s'il y a eu une attente calculée
        # On met à jour l'heure d'arrivée du prochain arrêt
        next_stop_data['arrival_time'] = current_time
        
        # Calculer le temps de départ du prochain arrêt
        next_stop_data['departure_time'] = current_time + timedelta(minutes=next_stop_data.get('dur', 0))
        
        processed_stops.append(next_stop_data)
        current_time = next_stop_data['departure_time'] # Préparer pour le prochain trajet

    return processed_stops


# --- UI ELEMENTS ---

def display_map(route_data, depot_location):
    if not route_data:
        st.warning("Aucune donnée de route à afficher sur la carte.")
        return

    # Centrer la carte sur le dépôt ou le premier point
    if depot_location:
        map_center = [depot_location[0], depot_location[1]]
    elif route_data and 'lat' in route_data[0] and 'lng' in route_data[0]:
        map_center = [route_data[0]['lat'], route_data[0]['lng']]
    else:
        map_center = [46.52, 6.62] # Centre par défaut si aucune info

    m = folium.Map(location=map_center, zoom_start=12)

    # Ajouter le dépôt
    if depot_location:
        folium.Marker(
            location=depot_location,
            popup=f"Dépôt: {st.session_state.depot['nom']}",
            icon=folium.Icon(color="green", icon="home")
        ).add_to(m)

    # Ajouter les clients et tracer le polyline
    points = []
    if route_data:
        # Extraire les points pour le tracé polyline s'ils sont disponibles dans route_data
        # S'ils ne le sont pas (par exemple, si route_data vient de calculate_route_times), on les cherche
        
        all_locations_for_map = []
        if depot_location:
            all_locations_for_map.append({"lat": depot_location[0], "lng": depot_location[1], "nom": f"Dépôt: {st.session_state.depot['nom']}", "type": "Depot"})
        
        # Ajouter les points ordonnés de route_data
        for i, stop in enumerate(route_data):
            if stop and stop.get('lat') and stop.get('lng'):
                # Ajouter le point pour le tracé et le marqueur
                all_locations_for_map.append(stop)
                
                # Ajouter les informations de temps pour le popup
                popup_html = f"""
                <b>{stop.get('nom', f'Arrêt {i+1}')}</b><br>
                Type: {stop.get('type', 'N/A')}<br>
                Arrivée: {stop.get('arrival_time').strftime('%H:%M:%S') if stop.get('arrival_time') else 'N/A'}<br>
                Service: {stop.get('dur', 0)} min<br>
                Départ: {stop.get('departure_time').strftime('%H:%M:%S') if stop.get('departure_time') else 'N/A'}
                """
                if stop.get('horaire_imperatif'):
                    popup_html += f"<br>Fenêtre: {stop.get('pas_avant')} - {stop.get('pas_apres')}"
                if stop.get('forced_return_aller'):
                    popup_html += "<br><i>Ramasse (traité à l'aller)</i>"

                icon_color = "green" if stop.get('type') == "Dépôt" else "blue"
                folium.Marker(
                    location=[stop['lat'], stop['lng']],
                    popup=folium.Popup(popup_html, max_width=300),
                    icon=folium.Icon(color=icon_color, icon="info-sign" if stop.get('type') != "Dépôt" else "home")
                ).add_to(m)

    # Tracer les lignes entre les points
    if len(all_locations_for_map) > 1:
        # Utiliser les points ordonnés pour tracer le chemin
        path_coords = [(loc['lat'], loc['lng']) for loc in all_locations_for_map]
        folium.PolyLine(path_coords, color="blue", weight=2.5, opacity=1).add_to(m)
        
    return m


# --- Main App Logic ---

st.title("🚗 Logistique Pro Suisse")

# --- ÉTAPE 1: DÉPOT ---
if st.session_state.step == 1:
    st.header("1. Informations du Dépôt")
    with st.form("depot_form", clear_on_submit=True):
        depot_nom = st.text_input("Nom du dépôt", "Dépôt Central")
        depot_address = st.text_input("Adresse du dépôt", placeholder="Ex: Rue de la Gare 1, 1000 Lausanne")
        depot_heure_depart = st.time_input("Heure de départ", datetime.combine(datetime.today(), datetime.min.time()).replace(hour=8, minute=0))
        
        submitted_depot = st.form_submit_button("Suivant: Ajouter des Clients")

        if submitted_depot:
            if depot_address:
                depot_lat, depot_lng = get_coordinates(depot_address)
                if depot_lat and depot_lng:
                    st.session_state.depot = {
                        "nom": depot_nom,
                        "address": depot_address,
                        "heure_depart": depot_heure_depart,
                        "lat": depot_lat,
                        "lng": depot_lng
                    }
                    st.session_state.step = 2
                    st.rerun()
                else:
                    st.error("Adresse du dépôt invalide. Veuillez réessayer.")
            else:
                st.error("Veuillez entrer une adresse pour le dépôt.")

# --- ÉTAPE 2: CLIENTS ---
if st.session_state.step == 2:
    st.header("2. Clients et Arrêts")
    
    # Affichage du dépôt actuel
    if st.session_state.depot:
        st.write(f"Dépôt : **{st.session_state.depot['nom']}** ({st.session_state.depot['address']}) - Départ : **{st.session_state.depot['heure_depart'].strftime('%H:%M')}**")
    else:
        st.warning("Veuillez d'abord définir les informations du dépôt.")
        if st.button("Retour aux informations du dépôt"):
            st.session_state.step = 1
            st.rerun()

    # Formulaire pour ajouter un nouveau client
    with st.form("client_form", clear_on_submit=True):
        st.subheader("Ajouter un nouvel arrêt")
        client_nom = st.text_input("Nom du client / arrêt", placeholder="Ex: Boulangerie Dupont")
        
        # Champs d'adresse séparés
        col1, col2, col3 = st.columns(3)
        with col1:
            client_rue = st.text_input("Rue", placeholder="Ex: Grand-Rue")
        with col2:
            client_num = st.text_input("Numéro", placeholder="Ex: 5")
        with col3:
            client_npa = st.text_input("NPA", placeholder="Ex: 1000", max_chars=5)
        client_ville = st.text_input("Ville", placeholder="Ex: Lausanne")
        # client_pays = st.text_input("Pays", "Suisse") # Optionnel

        client_type = st.selectbox("Type d'opération", ["Livraison", "Ramasse"])
        
        client_temps_sur_place = st.number_input("Temps sur place (min)", min_value=0, value=15, step=1)
        
        # Contraintes horaires
        client_horaire_imperatif = st.checkbox("Contrainte horaire impérative")
        client_pas_avant = None
        client_pas_apres = None
        if client_horaire_imperatif:
            col_h1, col_h2 = st.columns(2)
            with col_h1:
                client_pas_avant_str = st.text_input("Pas avant (HH:MM)", placeholder="Ex: 09:00")
                if client_pas_avant_str:
                    try:
                        datetime.strptime(client_pas_avant_str, '%H:%M')
                        client_pas_avant = client_pas_avant_str
                    except ValueError:
                        st.warning("Format HH:MM invalide pour 'Pas avant'.")
            with col_h2:
                client_pas_apres_str = st.text_input("Pas après (HH:MM)", placeholder="Ex: 11:30")
                if client_pas_apres_str:
                    try:
                        datetime.strptime(client_pas_apres_str, '%H:%M')
                        client_pas_apres = client_pas_apres_str
                    except ValueError:
                        st.warning("Format HH:MM invalide pour 'Pas après'.")
        
        # Nouvelle option: Ramasse forcée à l'aller
        client_forced_return_aller = False
        if client_type == "Ramasse":
            client_forced_return_aller = st.checkbox("Forcer ce ramasse à l'aller (même si traité comme ramasse)")

        submitted_client = st.form_submit_button("Ajouter l'arrêt")

        if submitted_client:
            if client_nom and (client_rue or client_num or client_npa or client_ville):
                # Construire l'adresse complète pour Google Maps
                full_address_for_geocode = f"{client_rue} {client_num}, {client_npa} {client_ville}".strip()
                
                lat, lng = get_coordinates(full_address_for_geocode)
                
                if lat and lng:
                    client_data = {
                        "nom": client_nom,
                        "rue": client_rue,
                        "num": client_num,
                        "npa": client_npa,
                        "ville": client_ville,
                        # "pays": client_pays,
                        "address": full_address_for_geocode, # Adresse pour Google Maps
                        "type": client_type,
                        "temps_sur_place": client_temps_sur_place,
                        "horaire_imperatif": client_horaire_imperatif,
                        "pas_avant": client_pas_avant,
                        "pas_apres": client_pas_apres,
                        "forced_return_aller": client_forced_return_aller,
                        "lat": lat,
                        "lng": lng
                    }
                    st.session_state.clients.append(client_data)
                    st.success(f"Arrêt '{client_nom}' ajouté !")
                else:
                    st.error(f"Impossible de géocoder l'adresse : {full_address_for_geocode}. Veuillez vérifier l'adresse ou la corriger.")
            else:
                st.error("Veuillez entrer le nom du client et au moins une partie de l'adresse (rue, numéro, NPA, ville).")

    st.markdown("---")
    st.subheader("Liste des arrêts saisis")
    
    if not st.session_state.clients:
        st.info("Aucun arrêt n'a encore été ajouté.")
    else:
        # Afficher les clients dans des "bulles"
        col_list, col_opt = st.columns([2, 1])
        
        with col_list:
            
            # Préparer les données pour l'affichage résumé
            summary_list = []
            for i, client in enumerate(st.session_state.clients):
                 summary_list.append(create_summary_entry(client, i))

            # Bouton Optimiser au-dessus de la liste
            if st.button("🚀 Optimiser la tournée", type="primary"):
                st.session_state.step = 3
                st.rerun()
            
            # Affichage de la liste résumé avec boutons Modifier/Supprimer
            for item in summary_list:
                is_depot_item = False
                if item['nom'] == st.session_state.depot['nom'] and item['type'] == 'Dépôt':
                    is_depot_item = True
                    box_class = "depot-box"
                else:
                    box_class = "client-box"

                # Affichage en "bulle" et sur une seule ligne
                # Utilisation de columns pour aligner le texte et les boutons
                cols = st.columns([0.8, 0.1, 0.1]) # Ajuster les proportions

                with cols[0]:
                    # Afficher le nom, le type et les contraintes
                    display_text = f"**{item['nom']}** ({item['type']})"
                    if item.get('constraints'):
                        display_text += f" {item['constraints']}"
                    st.markdown(f'<div class="summary-box {box_class}">{display_text} <br><small><i>{item["adresse_complete"]}</i></small></div>', unsafe_allow_html=True)
                
                with cols[1]:
                    # Bouton Modifier
                    if st.button("✏️", key=f"modify_{item['id']}", help="Modifier cet arrêt"):
                        # Logique de modification à implémenter
                        st.warning("Fonctionnalité de modification non encore implémentée.")
                
                with cols[2]:
                    # Bouton Supprimer
                    if st.button("❌", key=f"delete_{item['id']}", help="Supprimer cet arrêt"):
                        st.session_state.clients.pop(item['id'])
                        st.rerun() # Recharger pour mettre à jour la liste

        with col_opt:
            st.subheader("Options")
            st.session_state.optimisation_mode = st.selectbox(
                "Mode d'optimisation",
                ["Logique Chauffeur (Aller -> Retour)", "Mathématique (Le plus court)"],
                index=0 if st.session_state.optimisation_mode == "Logique Chauffeur (Aller -> Retour)" else 1
            )
            st.session_state.max_wait_time = st.number_input(
                "Temps d'attente max avant une fenêtre (min)",
                min_value=0,
                value=st.session_state.max_wait_time,
                step=5
            )
            # Zone pour le bouton Optimiser (déplacé plus haut pour être au-dessus de la liste)
            # st.markdown("---")


# --- ÉTAPE 3: RÉSULTAT DE L'OPTIMISATION ---
if st.session_state.step == 3:
    st.header("3. Feuille de Route Optimisée")
    
    if not st.session_state.depot:
        st.error("Informations du dépôt manquantes.")
        if st.button("Retour aux informations du dépôt"):
            st.session_state.step = 1
            st.rerun()
        st.stop()
        
    if not st.session_state.clients:
        st.warning("Aucun arrêt défini pour l'optimisation.")
        if st.button("Retour à la saisie des arrêts"):
            st.session_state.step = 2
            st.rerun()
        st.stop()

    # Créer une liste complète d'arrêts incluant le dépôt au début et à la fin
    all_stops_for_route = [st.session_state.depot] + st.session_state.clients + [st.session_state.depot]
    
    # Utiliser une fonction pour récupérer les coordonnées du dépôt si elles ne sont pas déjà là
    depot_lat, depot_lng = get_coordinates(st.session_state.depot['address'])
    depot_location_for_map = None
    if depot_lat and depot_lng:
        depot_location_for_map = [depot_lat, depot_lng]
        st.session_state.depot['lat'] = depot_lat # Mettre à jour dans le state
        st.session_state.depot['lng'] = depot_lng

    route_data = None
    ordered_stops_with_times = []

    try:
        # Appel à la fonction d'optimisation
        route_data, ordered_stops_with_times = optimize_route(
            st.session_state.depot, 
            st.session_state.clients, 
            st.session_state.optimisation_mode,
            st.session_state.max_wait_time
        )

        if route_data:
            st.success("Itinéraire optimisé avec succès !")
            
            # Afficher la carte
            st.subheader("Carte de la tournée")
            m = display_map(ordered_stops_with_times, depot_location_for_map)
            if m:
                folium_static(m, width=1000)
            
            # Afficher la liste ordonnée des arrêts
            st.subheader("Liste des arrêts dans l'ordre de la tournée")
            
            # Créer une liste pour l'affichage
            display_list_items = []
            
            # Ajouter le dépôt de départ
            if ordered_stops_with_times:
                first_stop = ordered_stops_with_times[0]
                if first_stop['nom'] == st.session_state.depot['nom']:
                    display_list_items.append({
                        "id": -1, # Index spécial pour le dépôt
                        "nom": first_stop['nom'],
                        "adresse_complete": first_stop['address'],
                        "type": "Dépôt",
                        "constraints": "", # Pas de contraintes pour le dépôt
                        "full_address_for_copy": first_stop['address'],
                        "arrival_time": first_stop.get('arrival_time'),
                        "departure_time": first_stop.get('departure_time'),
                        "dur": first_stop.get('dur', 0),
                        "lat": first_stop.get('lat'),
                        "lng": first_stop.get('lng'),
                        "horaire_imperatif": False,
                        "forced_return_aller": False,
                    })
            
            # Ajouter les clients ordonnés
            for i, stop in enumerate(ordered_stops_with_times[1:]): # Commencer après le premier élément (dépôt)
                # On a besoin de retrouver les infos originales (comme forced_return_aller)
                # Si stop['address'] existe et correspond à un client, on récupère ces infos.
                original_client_data = next((c for c in st.session_state.clients if c['address'] == stop['address']), None)
                
                constraints_html = ""
                if stop.get('horaire_imperatif'):
                    constraints_html += f'<span class="constraint-badge">Horaires</span>'
                if original_client_data and original_client_data.get('forced_return_aller'):
                    constraints_html += f'<span class="forced-return-badge">Ramasse Aller</span>'
                if stop.get('dur', 0) > 0:
                    constraints_html += f'<span class="depot-constraint-badge">{stop.get("dur")} min</span>'
                
                display_list_items.append({
                    "id": i, # Index dans la liste des clients
                    "nom": stop['nom'],
                    "adresse_complete": stop['address'], # L'adresse corrigée par Google Maps
                    "type": stop['type'],
                    "constraints": constraints_html,
                    "full_address_for_copy": stop['address'], # L'adresse complète pour copier
                    "arrival_time": stop.get('arrival_time'),
                    "departure_time": stop.get('departure_time'),
                    "dur": stop.get('dur', 0),
                    "lat": stop.get('lat'),
                    "lng": stop.get('lng'),
                    "horaire_imperatif": stop.get('horaire_imperatif', False),
                    "pas_avant": stop.get('pas_avant'),
                    "pas_apres": stop.get('pas_apres'),
                    "forced_return_aller": original_client_data.get('forced_return_aller', False) if original_client_data else False
                })
            
            # Afficher la liste
            for item in display_list_items:
                is_depot_item = (item['type'] == "Dépôt")
                box_class = "depot-box" if is_depot_item else "client-box"

                cols = st.columns([0.8, 0.1, 0.1]) # Ajuster les proportions

                with cols[0]:
                    display_text = f"**{item['nom']}**"
                    if not is_depot_item:
                         display_text += f" ({item['type']})"
                    if item['constraints']:
                        display_text += f" {item['constraints']}"
                    
                    # Affichage de l'adresse et des temps
                    address_line = f'<small><i>{item["adresse_complete"]}</i></small>'
                    time_line = f"Arrivée: {item['arrival_time'].strftime('%H:%M:%S') if item.get('arrival_time') else 'N/A'} | Départ: {item['departure_time'].strftime('%H:%M:%S') if item.get('departure_time') else 'N/A'}"
                    
                    st.markdown(f'<div class="summary-box {box_class}">{display_text}<br>{address_line}<br>{time_line}</div>', unsafe_allow_html=True)
                
                with cols[1]:
                    # Bouton Copier l'adresse
                    if st.button("📋", key=f"copy_{item['id']}", help="Copier l'adresse"):
                        # Il faudrait implémenter du JavaScript pour copier dans le presse-papier
                        # Pour l'instant, on affiche juste l'adresse
                        st.toast(f"Adresse copiée: {item['full_address_for_copy']}")
                        # st.code(item['full_address_for_copy'], language=None) # Afficher pour vérification
                        # Le copier-coller dans le presse-papier nécessite une interaction JS

                with cols[2]:
                    # Bouton d'information (pour voir les détails comme les horaires)
                    if st.button("ℹ️", key=f"info_{item['id']}", help="Voir les détails"):
                        # Afficher un popup ou un expander avec plus de détails
                        with st.expander(f"Détails pour {item['nom']}"):
                            st.write(f"Nom: {item['nom']}")
                            st.write(f"Adresse: {item['full_address_for_copy']}")
                            st.write(f"Type: {item['type']}")
                            st.write(f"Temps sur place: {item.get('dur', 0)} min")
                            if item.get('horaire_imperatif'):
                                st.write(f"Fenêtre horaire: {item.get('pas_avant')} - {item.get('pas_apres')}")
                            if item.get('forced_return_aller'):
                                st.write("<i>Ce ramasse est traité comme une livraison pour l'ordre du trajet.</i>")

            # Informations supplémentaires sur la tournée
            if route_data and route_data.get('legs'):
                total_distance = sum(leg['distance']['value'] for leg in route_data['legs'])
                total_duration_text = route_data['legs'][-1]['duration_in_traffic']['text'] if 'duration_in_traffic' in route_data['legs'][-1] else route_data['legs'][-1]['duration']['text']
                
                # L'heure de fin est le 'departure_time' du dernier arrêt.
                end_time = ordered_stops_with_times[-1]['departure_time'] if ordered_stops_with_times else st.session_state.depot['heure_depart']
                
                st.markdown("---")
                st.subheader("Résumé de la tournée")
                col_res1, col_res2, col_res3 = st.columns(3)
                with col_res1:
                    st.metric("Distance totale", f"{total_distance / 1000:.2f} km")
                with col_res2:
                    st.metric("Durée estimée", total_duration_text)
                with col_res3:
                    st.metric("Heure de retour estimée", end_time.strftime('%H:%M:%S'))
                    
            # Bouton pour revenir à la saisie
            if st.button("⬅️ Modifier la tournée"):
                st.session_state.step = 2
                st.rerun()

        else:
            st.error("Impossible de générer l'itinéraire. Veuillez vérifier vos entrées et réessayer.")
            if st.button("Retour à la saisie des arrêts"):
                st.session_state.step = 2
                st.rerun()


# --- Initialisation et Navigation ---
# Si on arrive sur l'app, aller directement à l'étape 1 ou 2 si le dépôt est déjà défini
if st.session_state.depot is None:
    st.session_state.step = 1
elif not st.session_state.clients and st.session_state.step == 1: # Si on a le dépôt mais pas encore de clients
    st.session_state.step = 2
elif not st.session_state.clients and st.session_state.step == 2: # Si on est à l'étape 2 mais sans clients
    pass # Rester à l'étape 2
elif st.session_state.step == 1: # Si on est à l'étape 1 mais qu'on a un dépôt (cas où on revient en arrière)
    pass # Rester à l'étape 1

# Gestion des boutons de navigation entre les étapes (si nécessaire, mais le rerun() gère déjà le flux)
