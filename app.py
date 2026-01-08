import streamlit as st
import pandas as pd
import googlemaps
import folium
from streamlit_folium import folium_static
import plotly.express as px
import datetime

# --- Configuration de la page ---
st.set_page_config(layout="wide", page_title="Optimisation Tournée")

# --- Initialisation du client Google Maps ---
# Assurez-vous que votre clé API est configurée dans .streamlit/secrets.toml
try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except Exception as e:
    st.error(f"Erreur lors de l'initialisation de Google Maps : {e}")
    st.stop()

# --- Fonctions Utilitaires ---

def geocode_address(address):
    """Géocode une adresse et retourne les coordonnées (latitude, longitude)."""
    try:
        geocode_result = gmaps.geocode(address)
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            return location['lat'], location['lng']
        else:
            return None, None
    except Exception as e:
        st.warning(f"Impossible de géocoder l'adresse '{address}' : {e}")
        return None, None

def calculate_distance_time(origin, destination):
    """Calcule la distance et le temps de trajet entre deux points."""
    try:
        directions_result = gmaps.directions(origin, destination, mode="driving")
        if directions_result:
            leg = directions_result[0]['legs'][0]
            distance = leg['distance']['value']  # en mètres
            duration = leg['duration']['value']  # en secondes
            return distance, duration
        else:
            return None, None
    except Exception as e:
        st.warning(f"Impossible de calculer la distance/temps entre {origin} et {destination} : {e}")
        return None, None

def format_duration(seconds):
    """Formate la durée en secondes en HH:MM:SS ou MM:SS."""
    if seconds is None:
        return "N/A"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    else:
        return f"{m:02d}:{s:02d}"

def format_distance(meters):
    """Formate la distance en mètres en km."""
    if meters is None:
        return "N/A"
    return f"{meters / 1000:.2f} km"

def get_address_details(address):
    """Récupère les détails d'une adresse incluant la ville et le code postal."""
    try:
        geocode_result = gmaps.geocode(address)
        if geocode_result:
            address_components = geocode_result[0]['address_components']
            city = ""
            postal_code = ""
            for component in address_components:
                if "locality" in component['types']:
                    city = component['long_name']
                if "postal_code" in component['types']:
                    postal_code = component['long_name']
            return city, postal_code
        else:
            return "", ""
    except Exception as e:
        st.warning(f"Impossible de récupérer les détails de l'adresse '{address}' : {e}")
        return "", ""


# --- Initialisation du State Management ---
if 'clients' not in st.session_state:
    st.session_state.clients = []
if 'clients_df' not in st.session_state:
    st.session_state.clients_df = pd.DataFrame(columns=['ID', 'Nom', 'Type', 'Adresse', 'Ville', 'Code Postal', 'Lat', 'Lng',
                                                      'Fenêtre Horaire Début', 'Fenêtre Horaire Fin', 'Temps de Service',
                                                      'Inclus Aller', 'Commentaires', 'Temps d\'Arrivée', 'Temps de Départ'])
if 'itineraire_optimise' not in st.session_state:
    st.session_state.itineraire_optimise = []
if 'map_center' not in st.session_state:
    st.session_state.map_center = [48.8566, 2.3522] # Paris par défaut

# --- Fonctions pour la Configuration de la Tournée ---

def add_client():
    """Ajoute un nouveau client à la liste."""
    st.session_state.clients.append({
        "id": len(st.session_state.clients) + 1,
        "nom": "",
        "type": "Livraison",
        "adresse": "",
        "ville": "",
        "code_postal": "",
        "lat": None,
        "lng": None,
        "fenetre_debut": None,
        "fenetre_fin": None,
        "temps_service": 0,
        "inclus_aller": False,
        "commentaires": "",
        "temps_arrivee": None,
        "temps_depart": None
    })
    # Met à jour le DataFrame en même temps
    update_clients_df()

def update_clients_df():
    """Met à jour le DataFrame à partir de la liste des clients."""
    if not st.session_state.clients:
        st.session_state.clients_df = pd.DataFrame(columns=['ID', 'Nom', 'Type', 'Adresse', 'Ville', 'Code Postal', 'Lat', 'Lng',
                                                          'Fenêtre Horaire Début', 'Fenêtre Horaire Fin', 'Temps de Service',
                                                          'Inclus Aller', 'Commentaires', 'Temps d\'Arrivée', 'Temps de Départ'])
        return

    data = []
    for client in st.session_state.clients:
        lat, lng = geocode_address(client["adresse"])
        client["lat"], client["lng"] = lat, lng
        if lat is not None and lng is not None:
            city, postal_code = get_address_details(client["adresse"])
            client["ville"], client["code_postal"] = city, postal_code
            st.session_state.map_center = [lat, lng] # Met à jour le centre de la carte

        # Conversion des heures en datetime.time pour une meilleure manipulation
        fenetre_debut_time = datetime.datetime.strptime(client["fenetre_debut"], '%H:%M').time() if client["fenetre_debut"] else None
        fenetre_fin_time = datetime.datetime.strptime(client["fenetre_fin"], '%H:%M').time() if client["fenetre_fin"] else None

        data.append({
            'ID': client["id"],
            'Nom': client["nom"],
            'Type': client["type"],
            'Adresse': client["adresse"],
            'Ville': client["ville"],
            'Code Postal': client["code_postal"],
            'Lat': client["lat"],
            'Lng': client["lng"],
            'Fenêtre Horaire Début': fenetre_debut_time,
            'Fenêtre Horaire Fin': fenetre_fin_time,
            'Temps de Service': client["temps_service"],
            'Inclus Aller': client["inclus_aller"],
            'Commentaires': client["commentaires"],
            'Temps d\'Arrivée': client["temps_arrivee"],
            'Temps de Départ': client["temps_depart"]
        })
    st.session_state.clients_df = pd.DataFrame(data)

def delete_client(client_id):
    """Supprime un client de la liste."""
    st.session_state.clients = [c for c in st.session_state.clients if c['id'] != client_id]
    update_clients_df()

def edit_client(client_id):
    """Affiche un formulaire pour éditer un client."""
    for client in st.session_state.clients:
        if client['id'] == client_id:
            with st.form(key=f"edit_form_{client_id}"):
                st.write(f"**Édition du client : {client['nom']}**")
                client['nom'] = st.text_input("Nom du client", client['nom'], key=f"nom_{client_id}")
                client['type'] = st.selectbox("Type de client", ["Livraison", "Ramasse"], client['type'], key=f"type_{client_id}")

                # Affichage conditionnel de l'option "Inclus Aller"
                if client['type'] == 'Ramasse':
                    client['inclus_aller'] = st.checkbox("Inclure ce ramasse dans le trajet aller", client['inclus_aller'], key=f"inclus_aller_{client_id}")
                else:
                    client['inclus_aller'] = False # Réinitialiser si ce n'est plus un ramasse

                client['adresse'] = st.text_input("Adresse", client['adresse'], key=f"adresse_{client_id}")
                client['fenetre_debut'] = st.text_input("Fenêtre horaire début (HH:MM)", client['fenetre_debut'], key=f"fenetre_debut_{client_id}")
                client['fenetre_fin'] = st.text_input("Fenêtre horaire fin (HH:MM)", client['fenetre_fin'], key=f"fenetre_fin_{client_id}")
                client['temps_service'] = st.number_input("Temps de service (minutes)", min_value=0, value=client['temps_service'], key=f"temps_service_{client_id}")
                client['commentaires'] = st.text_area("Commentaires", client['commentaires'], key=f"commentaires_{client_id}")

                if st.form_submit_button("Mettre à jour"):
                    update_clients_df()
                    st.success("Client mis à jour !")
                    st.experimental_rerun() # Force le rechargement pour voir les changements
            break

# --- Fonctions pour l'Optimisation ---

def optimize_route(clients, origin, destination):
    """Optimise la route en utilisant Google Maps Directions API."""
    if not clients:
        return [], None

    # Séparation des arrêts en fonction du type et de l'inclusion à l'aller
    livraisons = [c for c in clients if c['type'] == 'Livraison']
    ramasses_aller = [c for c in clients if c['type'] == 'Ramasse' and c['inclus_aller']]
    ramasses_retour = [c for c in clients if c['type'] == 'Ramasse' and not c['inclus_aller']]

    # L'ordre de visite est crucial : Garage -> Livraisons & Ramasses Aller -> Ramasses Retour -> Garage
    points_a_visiter = [origin] + livraisons + ramasses_aller + ramasses_retour + [destination]
    
    # Créer une liste d'adresses formatée pour l'API
    waypoints_addresses = [c['adresse'] for c in points_a_visiter[1:-1]] # Exclure origine et destination

    # Utilisation de l'optimisation de Google Maps si le nombre de waypoints le permet
    # Note: L'optimisation de Google Maps est limitée à 25 waypoints (23 arrêts + origine + destination)
    if len(waypoints_addresses) <= 23:
        try:
            directions_result = gmaps.directions(origin, destination,
                                                mode="driving",
                                                waypoints=waypoints_addresses,
                                                optimize_waypoints=True,
                                                departure_time=datetime.datetime.now()) # Départ maintenant

            if directions_result:
                optimized_order = directions_result[0]['waypoint_order']
                ordered_clients_full_path = [origin] + [clients[i] for i in optimized_order] + [destination] # Inclut les clients à leur ordre optimisé

                # Reconstruire la liste complète des clients dans l'ordre optimisé
                ordered_clients_final = []
                
                # Ajouter le garage (origine)
                ordered_clients_final.append(clients[0] if clients and clients[0]['nom'].lower() == 'garage' else {'nom': 'Garage', 'adresse': origin, 'type': 'Garage', 'lat': origin_coords[0], 'lng': origin_coords[1]}) # Assumer que le premier client est le garage si spécifié

                # Ajouter les clients dans l'ordre optimisé, en reconstruisant l'objet client
                waypoint_map = {c['adresse']: c for c in livraisons + ramasses_aller + ramasses_retour}
                
                for index in optimized_order:
                    waypoint_address = waypoints_addresses[index]
                    original_client_data = waypoint_map.get(waypoint_address)
                    if original_client_data:
                        # Créer une nouvelle entrée pour l'ordre optimisé
                        new_client_entry = original_client_data.copy()
                        new_client_entry['lat'], new_client_entry['lng'] = geocode_address(new_client_entry['adresse'])
                        ordered_clients_final.append(new_client_entry)

                # Ajouter le garage (destination)
                ordered_clients_final.append(clients[-1] if clients and clients[-1]['nom'].lower() == 'garage' else {'nom': 'Retour Garage', 'adresse': destination, 'type': 'Garage', 'lat': destination_coords[0], 'lng': destination_coords[1]}) # Assumer que le dernier client est le garage si spécifié

                # Calculer les temps d'arrivée et de départ pour chaque étape
                current_time = datetime.datetime.now()
                total_distance = 0
                total_duration = 0
                
                # Le premier point est le garage
                garage_data = next((c for c in clients if c['type'] == 'Garage'), None)
                if garage_data:
                    garage_data['temps_arrivee'] = current_time
                    garage_data['temps_depart'] = current_time
                    ordered_clients_final[0] = garage_data # S'assurer que le garage est bien le premier élément si il existe dans la liste clients

                for i in range(len(ordered_clients_final) - 1):
                    current_point = ordered_clients_final[i]
                    next_point = ordered_clients_final[i+1]

                    # Calculer le temps de trajet et la distance
                    distance, duration = calculate_distance_time(current_point['adresse'], next_point['adresse'])
                    if distance is not None and duration is not None:
                        total_distance += distance
                        total_duration += duration

                        # Calcul du temps de départ du point courant (incluant le temps de service)
                        departure_time_from_current = current_point['temps_depart'] if current_point['temps_depart'] else current_time
                        service_time = datetime.timedelta(minutes=current_point['temps_service'])
                        actual_departure_time = departure_time_from_current + service_time

                        # Calcul du temps d'arrivée au point suivant
                        arrival_time_at_next = actual_departure_time + datetime.timedelta(seconds=duration)

                        # Mise à jour des temps pour le point suivant
                        next_point['temps_arrivee'] = arrival_time_at_next
                        next_point['temps_depart'] = arrival_time_at_next # Le temps de départ est initialement le temps d'arrivée, sera mis à jour si temps de service

                        # Mettre à jour l'objet current_point avec ses temps calculés s'ils existent
                        if i == 0: # Pour le garage initial
                           current_point['temps_depart'] = actual_departure_time

                    else:
                        # Gérer le cas où le calcul de distance/temps échoue
                        next_point['temps_arrivee'] = "Erreur calcul"
                        next_point['temps_depart'] = "Erreur calcul"

                # Ajouter le dernier garage (destination)
                last_point = ordered_clients_final[-1]
                if last_point['type'] == 'Garage':
                    last_point['temps_arrivee'] = ordered_clients_final[-2]['temps_depart'] + datetime.timedelta(seconds=duration) if len(ordered_clients_final)>1 else datetime.datetime.now()
                    last_point['temps_depart'] = last_point['temps_arrivee'] # Fin de la tournée

                # Afficher les totaux
                st.session_state.total_distance = total_distance
                st.session_state.total_duration = total_duration

                return ordered_clients_final, directions_result[0]['routes'][0]['overview_polyline']['points']
            else:
                st.error("Impossible d'obtenir l'itinéraire.")
                return [], None
        except Exception as e:
            st.error(f"Erreur lors de l'appel à l'API Google Maps pour l'optimisation : {e}")
            return [], None
    else:
        st.warning("Trop de points pour utiliser l'optimisation automatique de Google Maps. L'ordre sera celui fourni.")
        # Ici, on pourrait implémenter une logique d'optimisation plus simple si nécessaire
        # Pour l'instant, on retourne les clients dans l'ordre où ils ont été entrés.
        
        # Calculer les temps d'arrivée et de départ pour chaque étape sans optimisation
        current_time = datetime.datetime.now()
        total_distance = 0
        total_duration = 0
        
        # Le premier point est le garage
        garage_data = next((c for c in clients if c['type'] == 'Garage'), None)
        if garage_data:
            garage_data['temps_arrivee'] = current_time
            garage_data['temps_depart'] = current_time
            
        for i in range(len(clients) - 1):
            current_point = clients[i]
            next_point = clients[i+1]

            distance, duration = calculate_distance_time(current_point['adresse'], next_point['adresse'])
            if distance is not None and duration is not None:
                total_distance += distance
                total_duration += duration

                departure_time_from_current = current_point['temps_depart'] if current_point['temps_depart'] else current_time
                service_time = datetime.timedelta(minutes=current_point['temps_service'])
                actual_departure_time = departure_time_from_current + service_time
                
                arrival_time_at_next = actual_departure_time + datetime.timedelta(seconds=duration)

                next_point['temps_arrivee'] = arrival_time_at_next
                next_point['temps_depart'] = arrival_time_at_next

        st.session_state.total_distance = total_distance
        st.session_state.total_duration = total_duration

        return clients, None # Pas de polyline à afficher sans optimisation


# --- Interface Streamlit ---

st.title("🚗 Configuration et Optimisation de Tournée")

# --- Section 1: Configuration Générale ---
with st.expander("Configuration Générale", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        origin_address = st.text_input("Adresse de départ (Garage)", "10 Rue de la République, Strasbourg")
        destination_address = st.text_input("Adresse de retour (Garage)", origin_address) # Par défaut, retour au même endroit
    with col2:
        departure_date = st.date_input("Date de la tournée", datetime.date.today())
        departure_time_str = st.text_input("Heure de départ (HH:MM)", "08:00")

    # Convertir l'heure de départ en datetime
    try:
        departure_hour, departure_minute = map(int, departure_time_str.split(':'))
        departure_datetime = datetime.datetime.combine(departure_date, datetime.time(departure_hour, departure_minute))
    except ValueError:
        st.error("Format d'heure invalide. Veuillez utiliser HH:MM.")
        departure_datetime = datetime.datetime.now() # Fallback


# --- Section 2: Liste des Clients / Arrêts ---
st.subheader("📍 Liste des Arrêts")

if st.button("Ajouter un arrêt"):
    add_client()

# Afficher les clients dans un format éditable
clients_to_display = sorted(st.session_state.clients, key=lambda c: c['id'])

if not clients_to_display:
    st.info("Aucun arrêt défini pour le moment. Cliquez sur 'Ajouter un arrêt' pour commencer.")
else:
    cols_header = st.columns([0.5, 2, 1, 1.5, 1, 1, 1, 0.5])
    cols_header[0].write("**ID**")
    cols_header[1].write("**Nom**")
    cols_header[2].write("**Type**")
    cols_header[3].write("**Adresse**")
    cols_header[4].write("**Fenêtres Horaires**")
    cols_header[5].write("**Temps Service (min)**")
    cols_header[6].write("**Actions**")

    for client in clients_to_display:
        cols = st.columns([0.5, 2, 1, 1.5, 1, 1, 0.5])
        cols[0].write(str(client['id']))
        cols[1].write(client['nom'])
        cols[2].write(client['type'])
        cols[3].write(client['adresse'])

        # Affichage des fenêtres horaires et temps de service avec formatage
        window_str = ""
        if client['fenetre_debut'] and client['fenetre_fin']:
            window_str = f"⌚ {client['fenetre_debut']} - {client['fenetre_fin']}"
        elif client['fenetre_debut']:
            window_str = f"⌚ dès {client['fenetre_debut']}"
        elif client['fenetre_fin']:
            window_str = f"⌚ avant {client['fenetre_fin']}"

        service_str = f"📍 {client['temps_service']} min"
        
        # Ajouter l'indicateur "Inclus Aller" pour les ramasses
        inclus_aller_str = ""
        if client['type'] == 'Ramasse' and client['inclus_aller']:
            inclus_aller_str = "⬆️ Aller"

        display_info = f"{window_str} {service_str} {inclus_aller_str}".strip()
        cols[4].write(display_info)

        cols[5].write(str(client['temps_service']))

        # Boutons d'action
        edit_col, delete_col, inclus_aller_col_checkbox = cols[6].columns(3) # Créer des colonnes pour mieux placer les éléments
        
        # Checkbox pour "Inclus Aller" si c'est un ramasse
        if client['type'] == 'Ramasse':
             # Utiliser une clé unique pour chaque checkbox
            checkbox_key = f"inclus_aller_list_{client['id']}"
            # Assurer que la valeur de la checkbox correspond à l'état du client
            client['inclus_aller'] = inclus_aller_col_checkbox.checkbox("Aller", value=client['inclus_aller'], key=checkbox_key)
        else:
            inclus_aller_col_checkbox.empty() # Ne rien afficher si ce n'est pas un ramasse

        edit_button_key = f"edit_button_{client['id']}"
        if edit_col.button("✏️", key=edit_button_key):
            edit_client(client['id'])

        delete_button_key = f"delete_button_{client['id']}"
        if delete_col.button("❌", key=delete_button_key):
            delete_client(client['id'])

    # Mettre à jour le DataFrame après avoir potentiellement modifié les valeurs de `inclus_aller` via les checkboxes
    # Il est important de faire cela avant la partie optimisation si les checkboxes sont utilisées
    update_clients_df() # S'assurer que le df est à jour avant l'optimisation

# --- Section 3: Carte ---
st.subheader("🗺️ Carte des Arrêts")
if st.session_state.clients_df is not None and not st.session_state.clients_df.empty:
    # Créer une carte Folium centrée sur le dernier point géocodé
    m = folium.Map(location=st.session_state.map_center, zoom_start=12)

    # Ajouter un marqueur pour le point de départ
    if origin_address:
        origin_coords = geocode_address(origin_address)
        if origin_coords[0] is not None:
            folium.Marker(
                location=origin_coords,
                popup=f"<b>Départ:</b> {origin_address}",
                icon=folium.Icon(color='green')
            ).add_to(m)

    # Ajouter des marqueurs pour chaque client
    for idx, row in st.session_state.clients_df.iterrows():
        if pd.notna(row['Lat']) and pd.notna(row['Lng']):
            popup_html = f"""
            <b>{row['Nom']}</b><br>
            Type: {row['Type']}<br>
            Adresse: {row['Adresse']}<br>
            Fenêtre Horaire: {row['Fenêtre Horaire Début'].strftime('%H:%M') if row['Fenêtre Horaire Début'] else 'N/A'} - {row['Fenêtre Horaire Fin'].strftime('%H:%M') if row['Fenêtre Horaire Fin'] else 'N/A'}<br>
            Temps de Service: {row['Temps de Service']} min<br>
            Inclus Aller: {'Oui' if row['Inclus Aller'] else 'Non'}
            """
            folium.Marker(
                location=[row['Lat'], row['Lng']],
                popup=folium.Popup(popup_html, max_width=300),
                icon=folium.Icon(color='blue' if row['Type'] == 'Livraison' else ('orange' if row['Type'] == 'Ramasse' else 'gray'))
            ).add_to(m)

    # Ajouter un marqueur pour le point de destination s'il est différent de l'origine
    if destination_address and destination_address != origin_address:
        destination_coords = geocode_address(destination_address)
        if destination_coords[0] is not None:
            folium.Marker(
                location=destination_coords,
                popup=f"<b>Destination:</b> {destination_address}",
                icon=folium.Icon(color='red')
            ).add_to(m)

    folium_static(m, width=700, height=400)
else:
    st.info("Veuillez ajouter des arrêts pour visualiser la carte.")


# --- Section 4: Optimisation de la Tournée ---
st.subheader("⚙️ Optimisation de la Tournée")

if st.button("Optimiser l'itinéraire"):
    # S'assurer que les coordonnées du garage sont disponibles
    origin_coords = geocode_address(origin_address)
    destination_coords = geocode_address(destination_address)

    if not origin_coords[0] or not destination_coords[0]:
        st.error("Veuillez vérifier les adresses de départ et de retour. Elles doivent être géocodables.")
    else:
        # Préparer les données pour l'optimisation
        # On ajoute une entrée pour le garage comme point de départ et de fin
        clients_for_optimization = []
        # Ajouter le garage comme premier point s'il n'est pas déjà dans la liste
        garage_client = next((c for c in st.session_state.clients if c['type'] == 'Garage'), None)
        if not garage_client:
             garage_client = {
                "id": 0, # ID spécial pour le garage
                "nom": "Garage",
                "type": "Garage",
                "adresse": origin_address,
                "ville": "", "code_postal": "",
                "lat": origin_coords[0], "lng": origin_coords[1],
                "fenetre_debut": None, "fenetre_fin": None,
                "temps_service": 0,
                "inclus_aller": False,
                "commentaires": "Point de départ et de retour",
                "temps_arrivee": departure_datetime, # Initialiser avec l'heure de départ de la tournée
                "temps_depart": departure_datetime
            }
             clients_for_optimization.append(garage_client)
        else: # Si le garage est déjà une entrée, s'assurer qu'elle est bien configurée et placée en premier
            garage_client['adresse'] = origin_address
            garage_client['lat'], garage_client['lng'] = origin_coords
            garage_client['temps_arrivee'] = departure_datetime
            garage_client['temps_depart'] = departure_datetime
            clients_for_optimization.append(garage_client)

        # Ajouter les clients existants
        clients_for_optimization.extend(st.session_state.clients)

        # Ajouter le garage comme destination finale s'il est différent du point de départ
        if origin_address != destination_address:
            final_garage_client = {
                "id": -1, # ID spécial pour le garage final
                "nom": "Retour Garage",
                "type": "Garage",
                "adresse": destination_address,
                "ville": "", "code_postal": "",
                "lat": destination_coords[0], "lng": destination_coords[1],
                "fenetre_debut": None, "fenetre_fin": None,
                "temps_service": 0,
                "inclus_aller": False,
                "commentaires": "Point de retour final",
                "temps_arrivee": None, # Sera calculé
                "temps_depart": None
            }
            clients_for_optimization.append(final_garage_client)
        
        # Appel à la fonction d'optimisation
        st.session_state.itineraire_optimise, polyline = optimize_route(clients_for_optimization, origin_address, destination_address)

        # Affichage des résultats de l'optimisation
        if st.session_state.itineraire_optimise:
            st.success("Itinéraire optimisé avec succès !")

            # Affichage du résumé
            st.write("### Résumé de la Tournée")
            st.write(f"**Distance totale :** {format_distance(st.session_state.total_distance)}")
            st.write(f"**Durée totale estimée :** {format_duration(st.session_state.total_duration)}")
            st.write(f"**Heure de départ :** {departure_datetime.strftime('%Y-%m-%d %H:%M')}")

            # Affichage de la carte avec l'itinéraire optimisé
            st.subheader("🗺️ Carte avec l'Itinéraire Optimisé")
            m_optimized = folium.Map(location=st.session_state.map_center, zoom_start=12)

            # Ajouter les marqueurs pour le départ et l'arrivée
            if origin_coords[0] is not None:
                folium.Marker(location=origin_coords, popup="Garage (Départ)", icon=folium.Icon(color='green')).add_to(m_optimized)
            if destination_coords[0] is not None and origin_address != destination_address:
                 folium.Marker(location=destination_coords, popup="Garage (Retour)", icon=folium.Icon(color='red')).add_to(m_optimized)

            # Dessiner la polyline si disponible
            if polyline:
                # Décoder la polyline fournie par Google Maps
                # La bibliothèque `polyline` doit être installée: pip install polyline
                try:
                    import polyline as poly # Renommage pour éviter conflit
                    decoded_polyline = poly.decode(polyline)
                    folium.PolyLine(decoded_polyline, color="blue", weight=2.5, opacity=1).add_to(m_optimized)

                    # Centrer la carte sur la polyline
                    if decoded_polyline:
                       m_optimized.fit_bounds(decoded_polyline)
                except ImportError:
                    st.warning("Le module 'polyline' n'est pas installé. Impossible d'afficher la polyline. Installez-le avec: pip install polyline")
                except Exception as e:
                    st.warning(f"Erreur lors du décodage ou de l'affichage de la polyline : {e}")

            # Ajouter les marqueurs pour les arrêts intermédiaires
            for client in st.session_state.itineraire_optimise:
                if client['type'] not in ['Garage']: # Ne pas redessiner les garages si déjà fait
                    if client['lat'] is not None and client['lng'] is not None:
                        popup_html = f"""
                        <b>{client['nom']}</b><br>
                        Type: {client['type']}<br>
                        Adresse: {client['adresse']}<br>
                        Heure d'arrivée: {client['temps_arrivee'].strftime('%H:%M:%S') if client['temps_arrivee'] else 'N/A'}<br>
                        Heure de départ: {client['temps_depart'].strftime('%H:%M:%S') if client['temps_depart'] else 'N/A'}<br>
                        Temps de Service: {client['temps_service']} min<br>
                        Inclus Aller: {'Oui' if client['inclus_aller'] else 'Non'}
                        """
                        folium.Marker(
                            location=[client['lat'], client['lng']],
                            popup=folium.Popup(popup_html, max_width=300),
                            icon=folium.Icon(color='blue' if client['type'] == 'Livraison' else ('orange' if client['type'] == 'Ramasse' else 'gray'))
                        ).add_to(m_optimized)

            folium_static(m_optimized, width=700, height=400)

            # Afficher le détail de l'itinéraire optimisé
            st.subheader("Détail de l'Itinéraire Optimisé")
            
            # Créer un DataFrame pour l'affichage détaillé
            itineraire_data = []
            for client in st.session_state.itineraire_optimise:
                 itineraire_data.append({
                    'Étape': client.get('id', ''), # Utiliser l'ID si disponible, sinon laisser vide
                    'Nom': client['nom'],
                    'Type': client['type'],
                    'Adresse': client['adresse'],
                    'Arrivée': client['temps_arrivee'].strftime('%H:%M:%S') if isinstance(client['temps_arrivee'], datetime.datetime) else client['temps_arrivee'],
                    'Départ': client['temps_depart'].strftime('%H:%M:%S') if isinstance(client['temps_depart'], datetime.datetime) else client['temps_depart'],
                    'Temps Service': client['temps_service'],
                    'Inclus Aller': 'Oui' if client['inclus_aller'] else 'Non'
                })
            
            itineraire_df = pd.DataFrame(itineraire_data)
            st.dataframe(itineraire_df)


        else:
            st.warning("L'itinéraire n'a pas pu être optimisé. Veuillez vérifier les adresses et les paramètres.")
