import streamlit as st
import googlemaps
from streamlit_folium import folium_static
import folium
from datetime import datetime, timedelta
import polyline
import pandas as pd # Ajout pour la gestion des données

# --- CONFIGURATION & STYLE ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

st.markdown("""
    <style>
    .summary-box { padding: 6px 12px; border-radius: 8px; margin-bottom: 5px; display: flex; align-items: center; color: white; font-size: 0.9rem; }
    .depot-box { background-color: #28a745; border: 1px solid #1e7e34; }
    .client-box { background-color: #0047AB; border: 1px solid #003380; }
    .warning-box { background-color: #ffc107; color: black; border: 1px solid #d39e00; }
    [data-testid="stHorizontalBlock"] { align-items: center; }
    .client-card { background-color: #0047AB; color: white; padding: 15px; border-radius: 10px 10px 0 0; margin-top: 10px; }
    .address-box { background-color: #0047AB; padding: 0 15px 10px 15px; border-radius: 0 0 10px 10px; margin-bottom: 10px; }
    .address-box code { color: white !important; background-color: transparent !important; font-size: 0.8rem;}
    .constraints-box { background-color: #17a2b8; color: white; padding: 10px; border-radius: 5px; margin-top: 5px; font-size: 0.9rem;}
    .constraints-box strong { color: #fff;}
    .order-info { font-size: 0.85rem; color: #ccc; margin-top: -10px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISATION GOOGLE MAPS ---
# Utilisation de st.secrets pour une clé API sécurisée
try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except Exception as e:
    st.error(f"Erreur lors de l'initialisation de l'API Google Maps: {e}")
    st.stop()

# --- SESSION STATE ---
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'clients' not in st.session_state:
    st.session_state.clients = []
if 'depot' not in st.session_state:
    st.session_state.depot = {}
if 'mode_optimisation' not in st.session_state:
    st.session_state.mode_optimisation = "Logique Chauffeur (Aller -> Retour)"
if 'step' not in st.session_state:
    st.session_state.step = 1

# --- FONCTIONS UTILITAIRES ---
def geocode_address(address):
    try:
        geocode_result = gmaps.geocode(address)
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            return location['lat'], location['lng']
        else:
            return None, None
    except Exception as e:
        st.warning(f"Erreur de géocodage pour '{address}': {e}")
        return None, None

def calculate_duration(origin_latlng, destination_latlng, mode="driving", departure_time=None):
    try:
        directions_result = gmaps.directions(origin_latlng,
                                             destination_latlng,
                                             mode=mode,
                                             departure_time=departure_time)
        if directions_result:
            return directions_result[0]['legs'][0]['duration']['value'] # en secondes
        else:
            return None
    except Exception as e:
        st.warning(f"Erreur de calcul de durée: {e}")
        return None

def calculate_distance(origin_latlng, destination_latlng, mode="driving"):
    try:
        directions_result = gmaps.directions(origin_latlng,
                                             destination_latlng,
                                             mode=mode)
        if directions_result:
            return directions_result[0]['legs'][0]['distance']['value'] # en mètres
        else:
            return None
    except Exception as e:
        st.warning(f"Erreur de calcul de distance: {e}")
        return None

def format_duration(seconds):
    if seconds is None:
        return "N/A"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}"

def format_distance(meters):
    if meters is None:
        return "N/A"
    return f"{meters / 1000:.2f} km"

# --- INTERFACE UTILISATEUR ---

st.title("🚚 Logistique Pro Suisse 🇨🇭")

# --- ÉTAPE 1 : SAISIE DES DONNÉES ---
if st.session_state.step == 1:
    st.header("📍 1. Votre Dépôt")
    with st.form("depot_form", clear_on_submit=True):
        depot_nom = st.text_input("Nom du dépôt", "Dépôt Central")
        depot_adresse_input = st.text_input("Adresse complète du dépôt", "Chemin de la Colline 1, 1023 Crissier")
        depot_heure_depart_str = st.text_input("Heure de départ (format HH:MM)", "08:00")

        submitted_depot = st.form_submit_button("Enregistrer le dépôt et passer aux clients")

        if submitted_depot:
            depot_lat, depot_lng = geocode_address(depot_adresse_input)
            if depot_lat and depot_lng:
                try:
                    depot_heure_depart = datetime.strptime(depot_heure_depart_str, "%H:%M")
                    st.session_state.depot = {
                        "nom": depot_nom,
                        "adresse": depot_adresse_input,
                        "lat": depot_lat,
                        "lng": depot_lng,
                        "heure_depart": depot_heure_depart
                    }
                    st.success("Dépôt enregistré !")
                    st.session_state.step = 2
                    st.rerun()
                except ValueError:
                    st.error("Format d'heure invalide. Utilisez HH:MM (ex: 08:00).")
            else:
                st.error("Impossible de géocoder l'adresse du dépôt. Veuillez vérifier.")

    st.markdown("---")

# --- ÉTAPE 2 : SAISIE DES CLIENTS ET CONTRAINTES ---
if st.session_state.step == 2:
    st.header("👤 2. Vos Clients et Arrêts")
    if not st.session_state.depot:
        st.warning("Veuillez d'abord enregistrer votre dépôt.")
        if st.button("Retour à l'étape 1"):
            st.session_state.step = 1
            st.rerun()
    else:
        st.write(f"Dépôt : **{st.session_state.depot['nom']}** ({st.session_state.depot['adresse']})")
        st.write(f"Heure de départ : **{st.session_state.depot['heure_depart'].strftime('%H:%M')}**")
        st.markdown("---")

        with st.form("clients_form", clear_on_submit=True):
            client_nom = st.text_input("Nom du client / Point d'arrêt")
            client_adresse = st.text_input("Adresse complète")

            col1, col2, col3 = st.columns(3)
            with col1:
                client_type = st.selectbox("Type", ["Livraison", "Ramasse"])
            with col2:
                client_duree_str = st.text_input("Temps sur place (min)", "15")
            with col3:
                # Nouvelle case pour les ramasses à considérer comme livraisons dans le calcul global
                consider_ramasse_as_livraison = st.checkbox("Ramasse à traiter comme Livraison", help="Cochez si cette ramasse doit être effectuée durant la 'phase aller' du trajet, en la traitant comme une livraison dans le calcul.")

            st.markdown("<div class='constraints-box'><strong>Contraintes Horaires (Optionnel)</strong></div>", unsafe_allow_html=True)
            client_contrainte_heure_debut_str = st.text_input("Fenêtre horaire début (HH:MM, laisser vide si aucune)", "")
            client_contrainte_heure_fin_str = st.text_input("Fenêtre horaire fin (HH:MM, laisser vide si aucune)", "")

            submitted_client = st.form_submit_button("Ajouter cet arrêt")

            if submitted_client and client_nom and client_adresse and client_duree_str:
                client_lat, client_lng = geocode_address(client_adresse)
                if client_lat and client_lng:
                    try:
                        client_duree = int(client_duree_str)
                        client_contrainte_debut = None
                        if client_contrainte_heure_debut_str:
                            client_contrainte_debut = datetime.strptime(client_contrainte_heure_debut_str, "%H:%M").time()

                        client_contrainte_fin = None
                        if client_contrainte_heure_fin_str:
                            client_contrainte_fin = datetime.strptime(client_contrainte_heure_fin_str, "%H:%M").time()

                        st.session_state.clients.append({
                            "nom": client_nom,
                            "adresse": client_adresse,
                            "lat": client_lat,
                            "lng": client_lng,
                            "type": client_type,
                            "duree": client_duree,
                            "contrainte_debut": client_contrainte_debut,
                            "contrainte_fin": client_contrainte_fin,
                            "consider_as_livraison": consider_ramasse_as_livraison # Ajout du flag
                        })
                        st.success(f"'{client_nom}' ajouté !")
                    except ValueError:
                        st.error("Durée ou heure invalide. Vérifiez vos saisies.")
                else:
                    st.error("Impossible de géocoder l'adresse. Veuillez vérifier.")

        st.markdown("---")
        st.header("🧳 Liste des arrêts à planifier")

        if not st.session_state.clients:
            st.info("Aucun arrêt ajouté pour le moment.")
        else:
            # Affichage des arrêts avec indications claires
            for i, client in enumerate(st.session_state.clients):
                full_address = f"{client['nom']} - {client['adresse']}"
                type_badge = ""
                constraints_text = ""

                if client['type'] == "Livraison":
                    type_badge = "<span style='background-color: #007bff; color: white; padding: 3px 6px; border-radius: 4px;'>Liv.</span>"
                else: # Ramasse
                    if client['consider_as_livraison']:
                        type_badge = "<span style='background-color: #28a745; color: white; padding: 3px 6px; border-radius: 4px;'>Ram. (Aller)</span>"
                    else:
                        type_badge = "<span style='background-color: #dc3545; color: white; padding: 3px 6px; border-radius: 4px;'>Ram.</span>"

                if client['contrainte_debut'] or client['contrainte_fin']:
                    constraints_text = f" <span class='warning-box'>⏰ {client['contrainte_debut'].strftime('%H:%M') if client['contrainte_debut'] else '--:--'} - {client['contrainte_fin'].strftime('%H:%M') if client['contrainte_fin'] else '--:--'}</span>"

                st.markdown(f"""
                <div class="client-box" style="margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong>{i+1}. {client['nom']}</strong> {type_badge}
                        <div>
                            {constraints_text}
                            <span style='background-color: #6c757d; color: white; padding: 3px 6px; border-radius: 4px;'>{client['duree']} min</span>
                        </div>
                    </div>
                    <div style="font-size: 0.8rem; color: #ddd;">{client['adresse']}</div>
                </div>
                """, unsafe_allow_html=True)

            col_mode, col_optimize = st.columns([1, 3])
            with col_mode:
                st.session_state.mode_optimisation = st.selectbox(
                    "Mode d'optimisation",
                    ["Logique Chauffeur (Aller -> Retour)", "Mathématique (Le plus court)"],
                    key="optimisation_select"
                )

            if st.button("🚀 Optimiser la Tournée"):
                st.session_state.step = 3
                st.rerun()

# --- ÉTAPE 3 : AFFICHAGE DE LA TOURNEE OPTIMISEE ---
if st.session_state.step == 3:
    st.header("🗺️ Votre Tournée Optimisée")

    if not st.session_state.depot or not st.session_state.clients:
        st.warning("Données incomplètes pour optimiser la tournée.")
        if st.button("Retour à la saisie"):
            st.session_state.step = 2
            st.rerun()
    else:
        depot = st.session_state.depot
        clients = st.session_state.clients
        mode = st.session_state.mode_optimisation

        # Préparation des données pour l'optimisation
        locations = [depot] + clients
        # On va créer une liste d'itinéraires potentiels et choisir le meilleur
        # Le calcul se fait à partir du dépôt

        # Créer la liste des points de passage pour le calcul des distances/temps
        points_a_visiter = []
        for client in clients:
            # On ajoute les clients qui sont des Livraisons OU des Ramasses marquées comme "Livraison" pour la phase aller
            if client["type"] == "Livraison" or client["consider_as_livraison"]:
                points_a_visiter.append(client)
        # Les autres ramasses seront traitées séparément après

        # 1. Calcul des points pour la phase Aller (Livraisons + Ramasses "traitées comme livraisons")
        optimized_route_aller = []
        current_time = depot["heure_depart"]
        last_location = depot

        if mode == "Logique Chauffeur (Aller -> Retour)":
            # Trie les points à visiter pour l'aller par distance croissante depuis le dépôt (Approximation)
            # Pour une vraie optimisation, il faudrait un TSP sur ces points.
            # Ici, on fait une approximation : plus proche du dépôt -> plus proche destination.

            # Utiliser une API pour obtenir les distances du dépôt à chaque point
            distance_matrix_origin = []
            for point in points_a_visiter:
                dist = calculate_distance([last_location['lat'], last_location['lng']], [point['lat'], point['lng']])
                distance_matrix_origin.append({'point': point, 'dist': dist})
            
            # Trie par distance croissante
            distance_matrix_origin.sort(key=lambda x: x['dist'] if x['dist'] is not None else float('inf'))
            
            ordered_points_aller = [item['point'] for item in distance_matrix_origin]

            # Ajouter les points à la route calculée
            for point in ordered_points_aller:
                # Calcul du temps de trajet DÉJÀ passé + temps de trajet vers ce point
                if last_location != depot: # Si on est déjà sur un point client
                    travel_time_seconds = calculate_duration([last_location['lat'], last_location['lng']], [point['lat'], point['lng']], departure_time=depot["heure_depart"].replace(hour=current_time.hour, minute=current_time.minute))
                else: # Premier trajet depuis le dépôt
                    travel_time_seconds = calculate_duration([last_location['lat'], last_location['lng']], [point['lat'], point['lng']], departure_time=depot["heure_depart"])
                
                travel_time = timedelta(seconds=travel_time_seconds if travel_time_seconds else 0)
                arrival_time = current_time + travel_time

                # Gestion des contraintes horaires (PRIORITÉ HORAIRE)
                # Si on arrive TROP TÔT
                if point['contrainte_debut'] and arrival_time.time() < point['contrainte_debut']:
                    wait_time = datetime.combine(datetime.today(), point['contrainte_debut']) - datetime.combine(datetime.today(), arrival_time.time())
                    arrival_time += wait_time
                    st.write(f"<div class='order-info'>Attente de {wait_time} à {point['nom']} (arrivée anticipée à {arrival_time.strftime('%H:%M')})</div>", unsafe_allow_html=True)
                
                # Si on arrive TROP TARD (contrainte de livraison - peut indiquer un problème)
                elif point['contrainte_fin'] and arrival_time.time() > point['contrainte_fin']:
                    # Ici, on pourrait déclencher une alerte, car on dépasse la fenêtre de livraison.
                    # Pour l'instant, on continue mais on enregistre le dépassement.
                    st.write(f"<div class='order-info'>Dépassement fenêtre horaire à {point['nom']} (arrivée à {arrival_time.strftime('%H:%M')}, fin de fenêtre {point['contrainte_fin'].strftime('%H:%M')})</div>", unsafe_allow_html=True)
                    # Optionnellement, on pourrait ajuster le temps de trajet suivant pour tenter de rattraper
                    
                
                departure_time_from_point = arrival_time + timedelta(minutes=point['duree'])
                optimized_route_aller.append({
                    "nom": point['nom'],
                    "adresse": point['adresse'],
                    "lat": point['lat'],
                    "lng": point['lng'],
                    "type": point['type'],
                    "duree": point['duree'],
                    "arrival_time": arrival_time,
                    "departure_time": departure_time_from_point,
                    "contrainte_debut": point['contrainte_debut'],
                    "contrainte_fin": point['contrainte_fin'],
                    "consider_as_livraison": point['consider_as_livraison'] # Pour référence
                })
                current_time = departure_time_from_point
                last_location = point
                
        elif mode == "Mathématique (Le plus court)":
            # Utilise l'API Google Maps pour l'optimisation TSP (Trading Salesperson Problem)
            # Nécessite de préparer les adresses dans un format que l'API comprend
            waypoints = [f"{c['lat']}, {c['lng']}" for c in points_a_visiter]
            origin = f"{depot['lat']}, {depot['lng']}"
            destination = origin # On revient au dépôt à la fin du calcul pour l'aller

            try:
                # On demande l'optimisation des waypoints
                directions_result = gmaps.directions(origin, destination,
                                                     mode="driving",
                                                     departure_time=depot["heure_depart"],
                                                     waypoints=waypoints,
                                                     optimize_waypoints=True)
                
                if directions_result:
                    optimized_order_indices = directions_result[0]['waypoint_order']
                    legs = directions_result[0]['legs']

                    # Reconstruction de la route optimisée
                    current_time = depot["heure_depart"]
                    last_leg_index = -1 # Pour suivre l'index dans `legs`

                    for i in optimized_order_indices:
                        client = points_a_visiter[i]
                        leg = legs[last_leg_index + 1] # Next leg in sequence

                        arrival_time = current_time + timedelta(seconds=leg['duration']['value'])

                        # Gestion des contraintes horaires (PRIORITÉ HORAIRE)
                        if client['contrainte_debut'] and arrival_time.time() < client['contrainte_debut']:
                            wait_time = datetime.combine(datetime.today(), client['contrainte_debut']) - datetime.combine(datetime.today(), arrival_time.time())
                            arrival_time += wait_time
                            st.write(f"<div class='order-info'>Attente de {wait_time} à {client['nom']} (arrivée anticipée à {arrival_time.strftime('%H:%M')})</div>", unsafe_allow_html=True)
                        elif client['contrainte_fin'] and arrival_time.time() > client['contrainte_fin']:
                            st.write(f"<div class='order-info'>Dépassement fenêtre horaire à {client['nom']} (arrivée à {arrival_time.strftime('%H:%M')}, fin de fenêtre {client['contrainte_fin'].strftime('%H:%M')})</div>", unsafe_allow_html=True)

                        departure_time_from_client = arrival_time + timedelta(minutes=client['duree'])

                        optimized_route_aller.append({
                            "nom": client['nom'],
                            "adresse": client['adresse'],
                            "lat": client['lat'],
                            "lng": client['lng'],
                            "type": client['type'],
                            "duree": client['duree'],
                            "arrival_time": arrival_time,
                            "departure_time": departure_time_from_client,
                            "contrainte_debut": client['contrainte_debut'],
                            "contrainte_fin": client['contrainte_fin'],
                            "consider_as_livraison": client['consider_as_livraison']
                        })
                        current_time = departure_time_from_client
                        last_leg_index += 1
                else:
                    st.error("Erreur lors de l'optimisation des waypoints par Google Maps.")
            except Exception as e:
                st.error(f"Une erreur est survenue lors de l'appel à l'API Google Directions: {e}")


        # 2. Calcul de la phase Retour (Ramasses non traitées comme livraisons)
        ramasses_retour = [c for c in clients if c['type'] == "Ramasse" and not c['consider_as_livraison']]
        optimized_route_retour = []
        current_time_retour = current_time # Commence là où l'aller s'est terminé
        last_location_retour = optimized_route_aller[-1] if optimized_route_aller else depot

        if ramasses_retour:
            # Trie les ramasses par distance DÉCROISSANTE depuis le dernier point de l'aller
            distance_matrix_retour = []
            for point in ramasses_retour:
                dist = calculate_distance([last_location_retour['lat'], last_location_retour['lng']], [point['lat'], point['lng']])
                distance_matrix_retour.append({'point': point, 'dist': dist})

            # Trie par distance croissante (pour un aller-retour plus logique)
            distance_matrix_retour.sort(key=lambda x: x['dist'] if x['dist'] is not None else float('inf'))

            ordered_points_retour = [item['point'] for item in distance_matrix_retour]

            for point in ordered_points_retour:
                # Calcul du temps de trajet
                travel_time_seconds = calculate_duration([last_location_retour['lat'], last_location_retour['lng']], [point['lat'], point['lng']], departure_time=depot["heure_depart"].replace(hour=current_time_retour.hour, minute=current_time_retour.minute))
                travel_time = timedelta(seconds=travel_time_seconds if travel_time_seconds else 0)
                arrival_time = current_time_retour + travel_time

                # Pas de contraintes horaires pour les ramasses dans cette version, mais on pourrait les ajouter.

                departure_time_from_point = arrival_time + timedelta(minutes=point['duree'])
                optimized_route_retour.append({
                    "nom": point['nom'],
                    "adresse": point['adresse'],
                    "lat": point['lat'],
                    "lng": point['lng'],
                    "type": point['type'],
                    "duree": point['duree'],
                    "arrival_time": arrival_time,
                    "departure_time": departure_time_from_point,
                    "contrainte_debut": None, # Pas de contraintes pour les ramasses dans cette implémentation
                    "contrainte_fin": None,
                    "consider_as_livraison": point['consider_as_livraison']
                })
                current_time_retour = departure_time_from_point
                last_location_retour = point

        # 3. Consolidation de la route finale
        final_route = optimized_route_aller + optimized_route_retour

        # Affichage de la liste des arrêts optimisés
        st.subheader("Ordre des arrêts :")

        m = folium.Map(location=[depot['lat'], depot['lng']], zoom_start=12)
        folium.Marker([depot['lat'], depot['lng']], popup=f"<b>{depot['nom']}</b><br>{depot['adresse']}", icon=folium.Icon(color='green')).add_to(m)

        total_duration_seconds = 0
        total_distance_meters = 0
        current_time_for_display = depot["heure_depart"]
        previous_location = (depot['lat'], depot['lng'])

        for i, stop in enumerate(final_route):
            display_type_badge = ""
            if stop['type'] == "Livraison":
                display_type_badge = "<span style='background-color: #007bff; color: white; padding: 2px 4px; border-radius: 3px;'>Liv.</span>"
            elif stop['type'] == "Ramasse":
                if stop['consider_as_livraison']:
                    display_type_badge = "<span style='background-color: #28a745; color: white; padding: 2px 4px; border-radius: 3px;'>Ram. (Aller)</span>"
                else:
                    display_type_badge = "<span style='background-color: #dc3545; color: white; padding: 2px 4px; border-radius: 3px;'>Ram.</span>"

            constraints_display = ""
            if stop['contrainte_debut'] or stop['contrainte_fin']:
                constraints_display = f" <strong>({stop['contrainte_debut'].strftime('%H:%M') if stop['contrainte_debut'] else '--:--'} - {stop['contrainte_fin'].strftime('%H:%M') if stop['contrainte_fin'] else '--:--'})</strong>"

            st.markdown(f"""
            <div class="client-box" style="margin-bottom: 5px; padding: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.9rem;">
                    <strong>{i+1}. {stop['nom']}</strong> {display_type_badge}
                    <div>
                        {constraints_display}
                        <span style='background-color: #6c757d; color: white; padding: 2px 4px; border-radius: 3px;'>{stop['duree']} min</span>
                    </div>
                </div>
                <div style="font-size: 0.75rem; color: #ddd;">{stop['adresse']}</div>
            </div>
            """, unsafe_allow_html=True)

            # Calcul de la durée et distance pour cette étape
            try:
                if i == 0: # Premier trajet depuis le dépôt
                    leg_info = gmaps.directions(f"{depot['lat']}, {depot['lng']}", f"{stop['lat']}, {stop['lng']}", mode="driving", departure_time=depot["heure_depart"])
                else:
                    leg_info = gmaps.directions(f"{previous_location[0]}, {previous_location[1]}", f"{stop['lat']}, {stop['lng']}", mode="driving", departure_time=current_time_for_display)

                if leg_info:
                    leg = leg_info[0]['legs'][0]
                    step_duration_seconds = leg['duration']['value']
                    step_distance_meters = leg['distance']['value']
                    total_duration_seconds += step_duration_seconds
                    total_distance_meters += step_distance_meters
                    
                    # Mise à jour de l'heure d'arrivée pour le prochain calcul
                    current_time_for_display = datetime.fromtimestamp(leg_info[0]['legs'][-1]['departure_time']['timestamp']) + timedelta(seconds=step_duration_seconds)
                    
                    folium.PolyLine(polyline.decode(leg_info[0]['overview_polyline']['points']), color="blue", weight=3, opacity=0.7).add_to(m)
                    folium.Marker([stop['lat'], stop['lng']],
                                  popup=f"<b>{stop['nom']}</b><br>{stop['arrival_time'].strftime('%H:%M')} - {stop['departure_time'].strftime('%H:%M')}",
                                  icon=folium.Icon(color="blue")).add_to(m)
                    previous_location = (stop['lat'], stop['lng'])
                else:
                    st.warning(f"Impossible de calculer l'itinéraire vers {stop['nom']}.")

            except Exception as e:
                st.warning(f"Erreur lors du calcul de l'itinéraire vers {stop['nom']}: {e}")
                current_time_for_display += timedelta(minutes=stop['duree']) # Avance du temps pour la suite

        st.markdown("---")
        st.subheader("Résumé de la Tournée")
        st.markdown(f"""
        <div class="summary-box depot-box">
            <strong>Dépôt Départ :</strong> {depot['nom']} à {depot['heure_depart'].strftime('%H:%M')}
        </div>
        <div class="summary-box client-box">
            <strong>Arrivée Finale (approx) :</strong> {current_time_for_display.strftime('%H:%M')}
        </div>
        <div class="summary-box depot-box">
            <strong>Durée Totale (trajets + arrêts) :</strong> {format_duration(total_duration_seconds + sum(c['duree'] for c in final_route))}
        </div>
        <div class="summary-box client-box">
            <strong>Distance Totale :</strong> {format_distance(total_distance_meters)}
        </div>
        """, unsafe_allow_html=True)


        folium_static(m, width=1000)

        if st.button("⬅️ Modifier la Tournée"):
            st.session_state.step = 2
            st.rerun()
