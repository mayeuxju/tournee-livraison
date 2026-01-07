import streamlit as st
import googlemaps
from streamlit_folium import folium_static
import folium
from datetime import datetime, timedelta
import polyline
import time # Ce module était là dans votre code, je le garde par précaution

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
    .address-box code { color: white !important; background-color: rgba(255,255,255,0.2) !important; border: none !important; }
    .badge { padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; margin-left: 10px; background: rgba(255,255,255,0.2); }
    .info-box { background-color: #f0f2f6; border-left: 5px solid #0047AB; padding: 5px 10px; margin-bottom: 10px; border-radius: 0 5px 5px 0;}
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISATION ---
if 'stops' not in st.session_state: st.session_state.stops = []
if 'step' not in st.session_state: st.session_state.step = 1
if 'vehicle' not in st.session_state: st.session_state.vehicle = "Voiture"
if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None
if 'algo' not in st.session_state: st.session_state.algo = "Logique Chauffeur (Aller -> Retour)" # Valeur par défaut

def reset_form_fields():
    # Reset pour un nouveau dépôt ou client
    st.session_state.f_nom = ""
    st.session_state.f_num = ""
    st.session_state.f_rue = ""
    st.session_state.f_npa = ""
    st.session_state.f_vil = ""
    st.session_state.f_type = "Livraison" # Défaut pour nouveau client
    st.session_state.f_dur = 15 # Défaut pour nouveau client
    st.session_state.f_use_h = False # Défaut pour nouveau client
    st.session_state.f_t1 = datetime.strptime("08:00", "%H:%M").time() # Défaut pour nouveau client
    st.session_state.f_t2 = datetime.strptime("18:00", "%H:%M").time() # Défaut pour nouveau client
    st.session_state.f_hdep = datetime.strptime("08:00", "%H:%M").time() # Défaut pour le dépôt
    st.session_state.f_consider_as_delivery = False # Nouveau champ pour ramasse
    st.session_state.edit_idx = None

# Initialiser les champs du formulaire si absents (pour éviter les erreurs sur la première exécution)
if 'f_nom' not in st.session_state: reset_form_fields()

try:
    # Votre ligne API spécifique ici
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except Exception as e:
    st.error(f"⚠️ Clé API Google manquante ou invalide. Vérifiez votre fichier secrets.toml. Erreur: {e}")
    st.stop()

def validate_address(n, r, npa, v):
    # Fonction pour valider et récupérer les coordonnées d'une adresse
    query = f"{r} {n} {npa} {v}, Suisse".strip()
    try:
        res = gmaps.geocode(query)
        if res:
            full_addr = res[0]['formatted_address']
            display_addr = full_addr.replace(", Suisse", "").replace(", Switzerland", "")
            return {
                "full": full_addr, "display": display_addr,
                "lat": res[0]['geometry']['location']['lat'],
                "lng": res[0]['geometry']['location']['lng'],
                "raw": {"n":n, "r":r, "npa":npa, "v":v} # Stocke les entrées brutes pour ré-édition facile
            }
    except Exception as e:
        st.warning(f"Impossible de géocoder l'adresse '{query}': {e}")
    return None

# --- ÉTAPE 1 : VÉHICULE ---
if st.session_state.step == 1:
    st.title("🚚 Type de transport")
    v = st.radio("Sélectionnez votre véhicule :", ["Voiture", "Camion (Lourd)"], index=["Voiture", "Camion (Lourd)"].index(st.session_state.vehicle))
    if st.button("Valider ➡️"):
        st.session_state.vehicle = v
        st.session_state.step = 2
        st.rerun()

# --- ÉTAPE 2 : CONFIGURATION DES ARRÊTS ---
elif st.session_state.step == 2:
    st.title(f"📍 Configuration de la tournée")
    
    col_form, col_map = st.columns([1, 1])

    with col_form:
        idx = st.session_state.edit_idx
        is_edit = idx is not None
        # Détermine si on est en train d'éditer/ajouter le dépôt (index 0) ou un client
        is_depot = (not is_edit and len(st.session_state.stops) == 0) or (is_edit and idx == 0)

        st.subheader("🏠 Dépôt" if is_depot else "👤 Client")
        
        # Champs communs à dépôt et client
        st.session_state.f_nom = st.text_input("Nom / Enseigne", value=st.session_state.f_nom)
        c1, c2 = st.columns([1, 3])
        st.session_state.f_num = c1.text_input("N°", value=st.session_state.f_num)
        st.session_state.f_rue = c2.text_input("Rue", value=st.session_state.f_rue)
        c3, c4 = st.columns(2)
        st.session_state.f_npa = c3.text_input("NPA", value=st.session_state.f_npa)
        st.session_state.f_vil = c4.text_input("Ville", value=st.session_state.f_vil)
        
        # Champs spécifiques au dépôt
        if is_depot:
            st.session_state.f_hdep = st.time_input("Heure de départ", value=st.session_state.f_hdep)
        # Champs spécifiques aux clients
        else:
            cc1, cc2 = st.columns(2)
            st.session_state.f_type = cc1.selectbox("Type de mission", ["Livraison", "Ramasse"], index=["Livraison", "Ramasse"].index(st.session_state.f_type))
            st.session_state.f_dur = cc2.number_input("Temps estimé sur place (min)", 5, 120, value=st.session_state.f_dur)
            
            # Gestion des contraintes horaires
            st.session_state.f_use_h = st.checkbox("Horaire impératif", value=st.session_state.f_use_h)
            if st.session_state.f_use_h:
                ca, cb = st.columns(2)
                st.session_state.f_t1 = ca.time_input("Pas avant", value=st.session_state.f_t1)
                st.session_state.f_t2 = cb.time_input("Pas après", value=st.session_state.f_t2)
            
            # Nouvelle case pour "Ramasse Cachée"
            if st.session_state.f_type == "Ramasse":
                 st.session_state.f_consider_as_delivery = st.checkbox("Considérer comme Livraison (pour le calcul d'itinéraire)", value=st.session_state.f_consider_as_delivery)

        # Bouton pour enregistrer l'arrêt
        if st.button("✅ Enregistrer", type="primary", use_container_width=True):
            res_addr = validate_address(st.session_state.f_num, st.session_state.f_rue, st.session_state.f_npa, st.session_state.f_vil)
            if res_addr:
                stop_data = {
                    "nom": st.session_state.f_nom or (f"Client {len(st.session_state.stops)}" if not is_depot else "DÉPÔT"),
                    **res_addr # Ajoute 'full', 'display', 'lat', 'lng', 'raw'
                }
                
                if is_depot:
                    stop_data["h_dep"] = st.session_state.f_hdep
                    stop_data["type"] = "Dépôt" # Ajout du type pour clarté
                else:
                    # Ajout des infos client
                    stop_data.update({
                        "type": st.session_state.f_type,
                        "use_h": st.session_state.f_use_h,
                        "dur": st.session_state.f_dur,
                        "t1": st.session_state.f_t1,
                        "t2": st.session_state.f_t2,
                        "consider_as_delivery": st.session_state.f_consider_as_delivery # Stockage du nouveau champ
                    })
                
                if is_edit:
                    st.session_state.stops[idx] = stop_data
                else:
                    st.session_state.stops.append(stop_data)
                
                reset_form_fields() # Réinitialise les champs du formulaire après ajout/modif
                st.rerun() # Rafraîchit l'UI pour montrer le nouvel arrêt
            else:
                st.error("L'adresse fournie n'a pas pu être validée. Veuillez vérifier les informations.")

        # Bouton pour lancer l'optimisation
        if len(st.session_state.stops) > 1: # On a besoin d'au moins un dépôt et un client
            st.write("---")
            st.subheader("🚀 Optimisation")
            # Votre radio button existant pour choisir l'algorithme
            algo_options = ["Logique Chauffeur (Aller -> Retour)", "Mathématique (Le plus court)"]
            current_algo_index = algo_options.index(st.session_state.algo) if st.session_state.algo in algo_options else 0
            algo = st.radio("Stratégie de tournée :", 
                           algo_options,
                           index=current_algo_index,
                           help="Le mode 'Logique' livre toutes les livraisons à l'aller et fait les ramasses au retour. Cochez 'Considérer comme Livraison' pour les ramasses que vous voulez traiter à l'aller.")
            
            if st.button("CALCULER L'ITINÉRAIRE", use_container_width=True, type="primary"):
                st.session_state.algo = algo # Sauvegarde du choix de l'algo
                st.session_state.step = 3 # Passe à l'étape suivante pour afficher les résultats
                st.rerun()

        # Affichage de la liste des arrêts actuels
        st.subheader("📋 Liste des arrêts")
        if not st.session_state.stops:
            st.info("Aucun arrêt configuré pour le moment.")
        else:
            for i, s in enumerate(st.session_state.stops):
                color_class = "depot-box" if i == 0 else "client-box"
                # Utilisation de vos classes CSS existantes pour l'affichage
                st.markdown(f'<div class="summary-box {color_class}">', unsafe_allow_html=True)
                cols = st.columns([0.05, 0.75, 0.1, 0.1]) # Colonnes pour l'icône/numéro, le nom/adresse, edit, delete
                
                # Icône/Numéro
                icon = "🏠" if i == 0 else f"{i}"
                cols[0].write(icon)
                
                # Nom et adresse du client/dépôt
                type_tag = ""
                if i > 0: # Uniquement pour les clients
                    is_delivery = (s['type'] == "Livraison") or s.get('consider_as_delivery', False) # Prend en compte la nouvelle option
                    type_text = "📦 Liv." if is_delivery else "🔄 Ram."
                    type_tag = f'<span class="badge">{type_text}</span>'
                
                # Affichage de l'adresse et du badge type
                display_name = s.get("nom", f"Arrêt {i}") # Sécurité si nom manquant
                cols[1].markdown(f"**{display_name}** | {s['display']} {type_tag}", unsafe_allow_html=True)
                
                # Boutons d'édition et de suppression
                if cols[2].button("✏️", key=f"ed_{i}"):
                    st.session_state.edit_idx = i
                    # Remplissage des champs du formulaire avec les données de l'arrêt à éditer
                    st.session_state.f_nom = s.get('nom', '')
                    st.session_state.f_num = s['raw']['n']
                    st.session_state.f_rue = s['raw']['r']
                    st.session_state.f_npa = s['raw']['npa']
                    st.session_state.f_vil = s['raw']['v']
                    if i == 0: # C'est le dépôt
                        st.session_state.f_hdep = s.get('h_dep', datetime.strptime("08:00", "%H:%M").time())
                    else: # C'est un client
                        st.session_state.f_type = s.get('type', 'Livraison')
                        st.session_state.f_dur = s.get('dur', 15)
                        st.session_state.f_use_h = s.get('use_h', False)
                        st.session_state.f_t1 = s.get('t1', datetime.strptime("08:00", "%H:%M").time())
                        st.session_state.f_t2 = s.get('t2', datetime.strptime("18:00", "%H:%M").time())
                        st.session_state.f_consider_as_delivery = s.get('consider_as_delivery', False) # Remplissage du nouveau champ
                    st.rerun() # Rafraîchit pour afficher le formulaire pré-rempli
                
                if cols[3].button("🗑️", key=f"dl_{i}"):
                    st.session_state.stops.pop(i)
                    st.rerun() # Rafraîchit pour retirer l'arrêt
                st.markdown('</div>', unsafe_allow_html=True)

    # Carte des arrêts sur la droite
    with col_map:
        if st.session_state.stops: # Afficher seulement si il y a des arrêts
            m = folium.Map(location=[st.session_state.stops[0]['lat'], st.session_state.stops[0]['lng']], zoom_start=10)
            for i, s in enumerate(st.session_state.stops):
                # Icône verte pour le dépôt, bleue pour les clients
                icon_color = "green" if i == 0 else "blue"
                folium.Marker([s['lat'], s['lng']], tooltip=f"{s.get('nom', 'Arrêt')} ({s['display']})", icon=folium.Icon(color=icon_color, icon='info-sign' if i==0 else 'user')).add_to(m)
            folium_static(m, width=600)
        else:
            st.info("La carte apparaîtra une fois que vous aurez ajouté des arrêts.")

# --- ÉTAPE 3 : RÉSULTATS DE L'OPTIMISATION ---
elif st.session_state.step == 3:
    st.title("🏁 Itinéraire Optimisé")
    
    # Paramètres pour le calcul
    t_mult = 1.25 if st.session_state.vehicle == "Camion (Lourd)" else 1.0 # Facteur pour les camions
    depot = st.session_state.stops[0]
    clients = st.session_state.stops[1:] # Tous les arrêts sauf le dépôt

    if not clients:
        st.warning("Aucun client ajouté. Impossible de calculer l'itinéraire.")
        if st.button("⬅️ Revenir à la configuration"):
            st.session_state.step = 2
            st.rerun()
        st.stop() # Arrête l'exécution ici si pas de clients

    ordered_clients = []
    waypoints_full_address = []
    
    # --- LOGIQUE DE TRI SELON L'ALGORITHME CHOISI ---
    if st.session_state.algo == "Logique Chauffeur (Aller -> Retour)":
        # Séparation des livraisons et ramasses
        livraisons_data = [c for c in clients if c['type'] == "Livraison" or c.get('consider_as_delivery', False)]
        ramasses_data = [c for c in clients if c['type'] == "Ramasse" and not c.get('consider_as_delivery', False)]
        
        # Tri des livraisons : du plus proche au plus loin du dépôt (à vol d'oiseau pour la logique)
        # Ceci est une simplification, Google Maps ne prendra pas forcément ce chemin s'il n'est pas optimal
        livraisons_data.sort(key=lambda x: ((x['lat']-depot['lat'])**2 + (x['lng']-depot['lng'])**2))
        # Tri des ramasses : du plus loin au plus proche du dépôt (pour le retour)
        ramasses_data.sort(key=lambda x: ((x['lat']-depot['lat'])**2 + (x['lng']-depot['lng'])**2), reverse=True)
        
        ordered_clients = livraisons_data + ramasses_data
        waypoints_full_address = [c['full'] for c in ordered_clients]
        
        # On demande à Google de calculer le trajet dans cet ordre PRÉCIS (sans ré-optimiser les waypoints eux-mêmes)
        # optimize_waypoints=False est CRUCIAL ici pour forcer l'ordre défini
        res = gmaps.directions(depot['full'], depot['full'], waypoints=waypoints_full_address, optimize_waypoints=False)

    else: # Algorithme "Mathématique (Le plus court)"
        # Utilise la fonction optimize_waypoints=True de Google Maps
        waypoints_full_address = [c['full'] for c in clients]
        res = gmaps.directions(depot['full'], depot['full'], waypoints=waypoints_full_address, optimize_waypoints=True)
        
        # Google renvoie l'ordre des waypoints dans 'waypoint_order'
        order_indices = res[0]['waypoint_order']
        ordered_clients = [clients[i] for i in order_indices]

    # --- AFFICHAGE DES RÉSULTATS ---
    if res and res[0]['legs']:
        legs = res[0]['legs']
        
        # Initialisation du temps de départ
        current_time = datetime.combine(datetime.today(), depot['h_dep'])
        
        # Création de la carte
        m_final = folium.Map(location=[depot['lat'], depot['lng']], zoom_start=10)
        
        # Affichage du départ du dépôt
        depot_info = f"**DÉPART DU DÉPÔT : {current_time.strftime('%H:%M')}**"
        st.markdown(f'<div class="info-box">{depot_info}</div>', unsafe_allow_html=True)
        folium.Marker([depot['lat'], depot['lng']], tooltip="Dépôt", icon=folium.Icon(color="green", icon='home')).add_to(m_final)

        total_distance = 0
        total_duration_minutes = 0
        total_service_time = 0
        total_wait_time = 0
        
        # Itération sur chaque étape (trajet + service client)
        for i, leg in enumerate(legs): # Note: legs inclut le trajet vers le DERNIER waypoint ET le retour vers le dépôt. On ne prendra que les N premiers legs.
            
            client = ordered_clients[i] # Le client correspondant à ce leg
            
            # Durée du trajet (ajustée pour véhicule lourd)
            duration_sec = leg['duration']['value']
            distance_text = leg['distance']['text']
            
            # Calcul du temps de trajet effectif en tenant compte du type de véhicule
            adjusted_duration_mins = int((duration_sec / 60) * t_mult)
            
            # Calcul du temps d'arrivée au client
            arrival_time_at_client = current_time + timedelta(minutes=adjusted_duration_mins)
            
            # Gestion des contraintes horaires et du temps d'attente
            wait_time_mins = 0
            if client.get('use_h', False):
                start_constraint = datetime.combine(datetime.today(), client['t1'])
                end_constraint = datetime.combine(datetime.today(), client['t2'])
                
                if arrival_time_at_client < start_constraint:
                    wait_time_mins = (start_constraint - arrival_time_at_client).total_seconds() / 60
                    arrival_time_at_client = start_constraint # Le chauffeur attend
                elif arrival_time_at_client > end_constraint:
                    # Le chauffeur est en retard sur sa fenêtre horaire, on affiche l'heure réelle d'arrivée
                    # Pas d'attente à ajouter, mais on peut afficher un message d'alerte plus tard
                    pass 
            
            # Durée de service réelle (temps passé sur place + attente éventuelle)
            service_time_mins = wait_time_mins + client.get('dur', 15) # Utilise 'dur' ou la valeur par défaut

            # Mise à jour du temps courant pour le prochain départ
            current_time = arrival_time_at_client + timedelta(minutes=service_time_mins)

            # Affichage des détails de l'étape courante
            type_icon = "📦" if (client['type'] == "Livraison" or client.get('consider_as_delivery', False)) else "🔄"
            display_name = client.get("nom", f"Arrêt {i+1}")

            # Informations à afficher dans la bulle d'information
            info_text = f"**{i+1}. {type_icon} {display_name}**<br>"
            info_text += f"⌚ Arrivée prévue : **{arrival_time_at_client.strftime('%H:%M:%S')}**<br>"
            if wait_time_mins > 0:
                info_text += f"⏳ Attente : **{wait_time_mins:.0f} min**<br>"
            info_text += f"⏰ Temps sur place : **{client.get('dur', 15)} min** ({'Attente incluse' if wait_time_mins > 0 else 'Pas d\'attente'})<br>"
            if client.get('use_h', False):
                info_text += f"🕦 Fenêtre horaire : **{client['t1'].strftime('%H:%M')} - {client['t2'].strftime('%H:%M')}**"
            
            # Utilisation de vos classes pour l'affichage
            st.markdown(f'<div class="client-card"><h3 style="margin:0; color: white;">{display_name} {type_icon}</h3><p style="margin: 5px 0; opacity: 0.9;">{info_text}</p></div>', unsafe_allow_html=True)
            st.markdown('<div class="address-box">', unsafe_allow_html=True)
            st.code(client['full'], language=None)
            st.markdown('</div>', unsafe_allow_html=True)

            # Ajout du marqueur sur la carte
            folium.Marker([client['lat'], client['lng']], popup=display_name, icon=folium.Icon(color="blue", icon='info-sign')).add_to(m_final)
            
            # Ajout de la ligne de trajet sur la carte (pour le trajet précédent)
            if i > 0: # On ajoute la ligne depuis l'arrêt précédent
                prev_client = ordered_clients[i-1]
                # La ligne doit aller de prev_client à client. Google nous donne les points.
                # Pour simplifier, on utilise les points de la géométrie du leg précédent.
                if i-1 < len(legs): # On vérifie si on a bien un leg précédent
                    route_segment = legs[i-1]['geometry']['coordinates']
                    # On doit décoder les points pour folium si nécessaire, mais souvent c'est déjà une liste de [lng, lat]
                    # Assurons-nous que c'est bien du [lat, lng] pour folium
                    decoded_points = [(p[1], p[0]) for p in route_segment] # Inversion lat/lng et formatage
                    folium.PolyLine(decoded_points, color="blue", weight=5, opacity=0.7).add_to(m_final)

            # Cumul des totaux
            total_distance += leg['distance']['value']
            total_duration_minutes += adjusted_duration_mins
            total_service_time += service_time_mins
            total_wait_time += wait_time_mins

        # Ajout du dernier segment (retour au dépôt)
        if len(legs) > len(ordered_clients): # S'il y a bien un leg de retour final
            final_leg = legs[-1] # Le dernier leg est le retour au dépôt
            total_distance += final_leg['distance']['value']
            total_duration_minutes += int((final_leg['duration']['value'] / 60) * t_mult)
            # Affichage résumé final
            st.markdown("---")
            st.subheader("📊 Résumé de la tournée")
            st.markdown(f'<div class="info-box"><strong>Distance totale :</strong> {total_distance/1000:.1f} km</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="info-box"><strong>Durée des trajets :</strong> {total_duration_minutes:.0f} min (estimé véhicule {st.session_state.vehicle})</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="info-box"><strong>Temps total sur place (avec attentes) :</strong> {total_service_time:.0f} min</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="info-box"><strong>Temps d\'attente total :</strong> {total_wait_time:.0f} min</div>', unsafe_allow_html=True)
            
            final_departure_from_depot = datetime.combine(datetime.today(), depot['h_dep'])
            total_time_spent = total_service_time + total_duration_minutes
            st.markdown(f'<div class="info-box"><strong>Heure de retour estimée au dépôt :</strong> <b>{ (final_departure_from_depot + timedelta(minutes=total_time_spent)).strftime("%H:%M:%S") }</b></div>', unsafe_allow_html=True)

            # Affichage de la carte avec tout l'itinéraire
            # Il faut reconstruire la polyligne globale à partir des points des legs
            all_points = []
            for i, leg in enumerate(legs):
                # On ajoute les points du trajet
                segment_points = leg['geometry']['coordinates']
                # Assurez-vous que les points sont dans le bon format [lat, lng] pour folium
                formatted_segment = [(p[1], p[0]) for p in segment_points]
                all_points.extend(formatted_segment)

            if all_points:
                folium.PolyLine(all_points, color="blue", weight=5, opacity=0.7).add_to(m_final)
            
            st.markdown("---")
            st.subheader("📍 Carte de l'itinéraire")
            folium_static(m_final, width=1000)

        else: # Cas où il n'y a pas eu de retour au dépôt calculé (trop peu d'arrêts ?)
            st.warning("Impossible de calculer le trajet de retour au dépôt.")

        # Bouton pour revenir à la configuration
        if st.button("⬅️ Modifier la tournée"):
            st.session_state.step = 2
            st.rerun()
            
    else:
        st.error("Impossible de calculer l'itinéraire. Veuillez vérifier les adresses et votre clé API.")
        if st.button("⬅️ Revenir à la configuration"):
            st.session_state.step = 2
            st.rerun()
