import streamlit as st
import googlemaps
from streamlit_folium import folium_static
import folium
from datetime import datetime, timedelta
import polyline
import time

# --- CONFIGURATION & STYLE ---
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

# Style le plus proche possible de l'original. J'ai retiré mes ajouts de style.
st.markdown("""
    <style>
    /* Styles d'origine que vous avez fournis */
    .summary-box { padding: 6px 12px; border-radius: 8px; margin-bottom: 5px; display: flex; align-items: center; color: white; font-size: 0.9rem; }
    .depot-box { background-color: #0047AB; border: 1px solid #003380; } /* J'ai mis la couleur bleue d'origine pour le dépôt */
    .client-box { background-color: #0047AB; border: 1px solid #003380; } /* Idem pour les clients */
    [data-testid="stHorizontalBlock"] { align-items: center; }
    .client-card { background-color: #0047AB; color: white; padding: 15px; border-radius: 10px 10px 0 0; margin-top: 10px; }
    .address-box { background-color: #0047AB; padding: 0 15px 10px 15px; border-radius: 0 0 10px 10px; margin-bottom: 10px; }
    .address-box code { color: white !important; background-color: rgba(255,255,255,0.2) !important; border: none !important; }
    .badge { padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; margin-left: 10px; background: rgba(255,255,255,0.2); }
    
    /* Styles ajoutés pour les nouvelles infos, mais discrets */
    .time-info { font-size: 0.8rem; opacity: 0.9; margin-top: 3px; }
    .constraint-badge { padding: 1px 4px; border-radius: 3px; font-size: 0.6rem; background-color: rgba(255,255,255,0.3); margin-left: 5px;}
    .error-message { background-color: #dc3545; color: white; padding: 10px; border-radius: 5px; margin-top: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISATION ---
if 'stops' not in st.session_state: st.session_state.stops = []
if 'step' not in st.session_state: st.session_state.step = 1
if 'vehicle' not in st.session_state: st.session_state.vehicle = "Voiture"
if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None
if 'algo' not in st.session_state: st.session_state.algo = "Logique Chauffeur (Aller -> Retour)"

def reset_form_fields():
    st.session_state.f_nom = ""
    st.session_state.f_num = ""
    st.session_state.f_rue = ""
    st.session_state.f_npa = ""
    st.session_state.f_vil = ""
    st.session_state.f_type = "Livraison"
    st.session_state.f_dur = 15
    st.session_state.f_use_h = False
    st.session_state.f_t1 = datetime.strptime("08:00", "%H:%M").time()
    st.session_state.f_t2 = datetime.strptime("18:00", "%H:%M").time()
    st.session_state.f_hdep = datetime.strptime("08:00", "%H:%M").time()
    st.session_state.f_consider_as_delivery = False # Nouveau champ
    st.session_state.edit_idx = None

if 'f_nom' not in st.session_state: reset_form_fields()

try:
    gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
except Exception as e:
    st.error(f"⚠️ Clé API Google manquante. Vérifiez votre fichier secrets.toml. Erreur: {e}")
    st.stop()

def validate_address(n, r, npa, v):
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
                "raw": {"n":n, "r":r, "npa":npa, "v":v}
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
        is_depot = (not is_edit and len(st.session_state.stops) == 0) or (is_edit and idx == 0)

        st.subheader("🏠 Dépôt" if is_depot else "👤 Client")
        st.session_state.f_nom = st.text_input("Nom / Enseigne", value=st.session_state.f_nom)
        c1, c2 = st.columns([1, 3])
        st.session_state.f_num = c1.text_input("N°", value=st.session_state.f_num)
        st.session_state.f_rue = c2.text_input("Rue", value=st.session_state.f_rue)
        c3, c4 = st.columns(2)
        st.session_state.f_npa = c3.text_input("NPA", value=st.session_state.f_npa)
        st.session_state.f_vil = c4.text_input("Ville", value=st.session_state.f_vil)
        
        if is_depot:
            st.session_state.f_hdep = st.time_input("Heure de départ", value=st.session_state.f_hdep)
        else:
            cc1, cc2 = st.columns(2)
            st.session_state.f_type = cc1.selectbox("Type de mission", ["Livraison", "Ramasse"], index=["Livraison", "Ramasse"].index(st.session_state.f_type))
            st.session_state.f_dur = cc2.number_input("Temps estimé sur place (min)", 5, 120, value=st.session_state.f_dur)
            
            st.session_state.f_use_h = st.checkbox("Horaire impératif", value=st.session_state.f_use_h)
            if st.session_state.f_use_h:
                ca, cb = st.columns(2)
                st.session_state.f_t1 = ca.time_input("Pas avant", value=st.session_state.f_t1)
                st.session_state.f_t2 = cb.time_input("Pas après", value=st.session_state.f_t2)
            
            # NOUVEAU : Case pour "Considérer comme Livraison" pour les Ramasses
            if st.session_state.f_type == "Ramasse":
                 st.session_state.f_consider_as_delivery = st.checkbox("Considérer comme Livraison (pour le calcul d'itinéraire)", value=st.session_state.f_consider_as_delivery)

        if st.button("✅ Enregistrer", type="primary", use_container_width=True):
            res_addr = validate_address(st.session_state.f_num, st.session_state.f_rue, st.session_state.f_npa, st.session_state.f_vil)
            if res_addr:
                stop_data = {
                    "nom": st.session_state.f_nom or (f"Client {len(st.session_state.stops)}" if not is_depot else "DÉPÔT"),
                    **res_addr
                }
                
                if is_depot:
                    stop_data["h_dep"] = st.session_state.f_hdep
                    stop_data["type"] = "Dépôt"
                else:
                    stop_data.update({
                        "type": st.session_state.f_type,
                        "dur": st.session_state.f_dur,
                        "use_h": st.session_state.f_use_h,
                        "t1": st.session_state.f_t1,
                        "t2": st.session_state.f_t2,
                        "consider_as_delivery": st.session_state.f_consider_as_delivery # Stockage du nouveau champ
                    })
                
                if is_edit:
                    st.session_state.stops[idx] = stop_data
                else:
                    st.session_state.stops.append(stop_data)
                
                reset_form_fields()
                st.rerun()
            else:
                st.error("L'adresse fournie n'a pas pu être validée. Veuillez vérifier les informations.")

        if len(st.session_state.stops) > 1:
            st.write("---")
            st.subheader("🚀 Optimisation")
            algo_options = ["Logique Chauffeur (Aller -> Retour)", "Mathématique (Le plus court)"]
            current_algo_index = algo_options.index(st.session_state.algo) if st.session_state.algo in algo_options else 0
            algo = st.radio("Stratégie de tournée :", 
                           algo_options,
                           index=current_algo_index,
                           help="Le mode 'Logique' livre toutes les livraisons à l'aller et fait les ramasses au retour. Cochez 'Considérer comme Livraison' pour les ramasses que vous voulez traiter à l'aller.")
            
            if st.button("CALCULER L'ITINÉRAIRE", use_container_width=True, type="primary"):
                st.session_state.algo = algo
                st.session_state.step = 3
                st.rerun()

        st.subheader("📋 Liste des arrêts")
        if not st.session_state.stops:
            st.info("Aucun arrêt configuré pour le moment.")
        else:
            for i, s in enumerate(st.session_state.stops):
                color_class = "depot-box" if i == 0 else "client-box"
                st.markdown(f'<div class="summary-box {color_class}">', unsafe_allow_html=True)
                cols = st.columns([0.05, 0.75, 0.1, 0.1])
                
                icon = "🏠" if i == 0 else f"{i}"
                cols[0].write(icon)
                
                type_tag = ""
                type_info_display = "" # Pour afficher les infos horaires
                
                if i > 0: # Client
                    is_delivery = (s['type'] == "Livraison") or s.get('consider_as_delivery', False)
                    type_text = "📦 Liv." if is_delivery else "🔄 Ram."
                    type_tag = f'<span class="badge">{type_text}</span>'
                    
                    # Affichage des contraintes horaires directement ici
                    if s.get('use_h', False):
                        type_info_display += f'<span class="time-info">🕦 {s["t1"].strftime("%H:%M")}-{s["t2"].strftime("%H:%M")}</span>'
                        if s.get('dur', 0) > 0: # Ajout durée si présente
                            type_info_display += f'<span class="time-info"> | Durée: {s["dur"]} min</span>'
                    elif s.get('dur', 0) > 0: # Durée seule si pas de contrainte horaire
                         type_info_display += f'<span class="time-info">Durée: {s["dur"]} min</span>'


                display_name = s.get("nom", f"Arrêt {i}")
                
                # Markdown combiné pour le nom, l'adresse, le badge et les infos horaires
                cols[1].markdown(f"**{display_name}** | {s['display']} {type_tag}<br>{type_info_display}", unsafe_allow_html=True)
                
                if cols[2].button("✏️", key=f"ed_{i}"):
                    st.session_state.edit_idx = i
                    st.session_state.f_nom = s.get('nom', '')
                    st.session_state.f_num = s['raw']['n']
                    st.session_state.f_rue = s['raw']['r']
                    st.session_state.f_npa = s['raw']['npa']
                    st.session_state.f_vil = s['raw']['v']
                    if i == 0:
                        st.session_state.f_hdep = s.get('h_dep', datetime.strptime("08:00", "%H:%M").time())
                    else:
                        st.session_state.f_type = s.get('type', 'Livraison')
                        st.session_state.f_dur = s.get('dur', 15)
                        st.session_state.f_use_h = s.get('use_h', False)
                        st.session_state.f_t1 = s.get('t1', datetime.strptime("08:00", "%H:%M").time())
                        st.session_state.f_t2 = s.get('t2', datetime.strptime("18:00", "%H:%M").time())
                        st.session_state.f_consider_as_delivery = s.get('consider_as_delivery', False)
                    st.rerun()
                
                if cols[3].button("🗑️", key=f"dl_{i}"):
                    st.session_state.stops.pop(i)
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

    with col_map:
        if st.session_state.stops:
            m = folium.Map(location=[st.session_state.stops[0]['lat'], st.session_state.stops[0]['lng']], zoom_start=10)
            for i, s in enumerate(st.session_state.stops):
                icon_color = "green" if i == 0 else "blue"
                # Utilisation d'icônes standard plus simples pour rester proche de l'original
                folium.Marker([s['lat'], s['lng']], tooltip=f"{s.get('nom', 'Arrêt')} ({s['display']})", icon=folium.Icon(color=icon_color)).add_to(m)
            folium_static(m, width=600)
        else:
            st.info("La carte apparaîtra une fois que vous aurez ajouté des arrêts.")

# --- ÉTAPE 3 : RÉSULTATS DE L'OPTIMISATION ---
elif st.session_state.step == 3:
    st.title("🏁 Itinéraire Optimisé")
    
    t_mult = 1.25 if st.session_state.vehicle == "Camion (Lourd)" else 1.0
    depot = st.session_state.stops[0]
    clients = st.session_state.stops[1:]

    if not clients:
        st.warning("Aucun client ajouté. Impossible de calculer l'itinéraire.")
        if st.button("⬅️ Revenir à la configuration"):
            st.session_state.step = 2
            st.rerun()
        st.stop()

    ordered_clients = []
    waypoints_full_address = []
    
    # --- LOGIQUE DE TRI ---
    if st.session_state.algo == "Logique Chauffeur (Aller -> Retour)":
        livraisons_data = [c for c in clients if c['type'] == "Livraison" or c.get('consider_as_delivery', False)]
        ramasses_data = [c for c in clients if c['type'] == "Ramasse" and not c.get('consider_as_delivery', False)]
        
        livraisons_data.sort(key=lambda x: ((x['lat']-depot['lat'])**2 + (x['lng']-depot['lng'])**2))
        ramasses_data.sort(key=lambda x: ((x['lat']-depot['lat'])**2 + (x['lng']-depot['lng'])**2), reverse=True)
        
        ordered_clients = livraisons_data + ramasses_data
        waypoints_full_address = [c['full'] for c in ordered_clients]
        
        # Tentative de résoudre l'itinéraire AVEC l'ordre spécifié
        # Si ce mode cause l'erreur, c'est qu'il faut forcer optimize_waypoints=True
        # ou revoir la manière dont Google Maps interprète cet ordre.
        try:
            res = gmaps.directions(depot['full'], depot['full'], waypoints=waypoints_full_address, optimize_waypoints=False)
        except Exception as e:
            st.error(f"Erreur lors de la requête Directions API (Logique Chauffeur): {e}")
            st.session_state.step = 2 # Retour à la configuration
            st.rerun()

    else: # Algorithme "Mathématique (Le plus court)"
        waypoints_full_address = [c['full'] for c in clients]
        try:
            res = gmaps.directions(depot['full'], depot['full'], waypoints=waypoints_full_address, optimize_waypoints=True)
            order_indices = res[0]['waypoint_order']
            ordered_clients = [clients[i] for i in order_indices]
        except Exception as e:
            st.error(f"Erreur lors de la requête Directions API (Mathématique): {e}")
            st.session_state.step = 2
            st.rerun()

    # --- AFFICHAGE DES RÉSULTATS ---
    # --- CORRECTION DE L'ERREUR POSEANT PROBLÈME ---
    if res and res[0].get('legs'): # Vérifie que 'legs' existe dans la réponse
        legs = res[0]['legs']
        
        current_time = datetime.combine(datetime.today(), depot['h_dep'])
        m_final = folium.Map(location=[depot['lat'], depot['lng']], zoom_start=10)
        
        # Utilisation de votre style original pour l'en-tête DÉPART
        st.markdown(f'<div class="client-card"><h3 style="margin:0; color: white;">1. 🏠 DÉPART DÉPÔT</h3><p style="margin: 5px 0; opacity: 0.9;">Heure de départ : <b>{current_time.strftime("%H:%M")}</b></p></div>', unsafe_allow_html=True)
        st.markdown('<div class="address-box">', unsafe_allow_html=True)
        st.code(depot['full'], language=None)
        st.markdown('</div>', unsafe_allow_html=True)
        folium.Marker([depot['lat'], depot['lng']], tooltip="Dépôt", icon=folium.Icon(color="green")).add_to(m_final)

        total_distance = 0
        total_duration_minutes = 0
        total_service_time = 0
        total_wait_time = 0
        
        for i, leg in enumerate(legs):
            # On s'arrête si le nombre de legs est supérieur au nombre de clients (car le dernier leg est le retour au dépôt)
            if i >= len(ordered_clients): 
                break
                
            client = ordered_clients[i]
            
            duration_sec = leg['duration']['value']
            distance_text = leg['distance']['text']
            
            adjusted_duration_mins = int((duration_sec / 60) * t_mult)
            
            arrival_time_at_client = current_time + timedelta(minutes=adjusted_duration_mins)
            
            wait_time_mins = 0
            if client.get('use_h', False):
                start_constraint = datetime.combine(datetime.today(), client['t1'])
                end_constraint = datetime.combine(datetime.today(), client['t2'])
                
                if arrival_time_at_client < start_constraint:
                    wait_time_mins = (start_constraint - arrival_time_at_client).total_seconds() / 60
                    arrival_time_at_client = start_constraint
                #elif arrival_time_at_client > end_constraint: # Gérer le retard si nécessaire (ici, on ne fait qu'afficher)
                #    pass
            
            service_time_mins = wait_time_mins + client.get('dur', 15)

            # Affichage des informations (respectant votre style)
            type_icon = "📦" if (client['type'] == "Livraison" or client.get('consider_as_delivery', False)) else "🔄"
            display_name = client.get("nom", f"Arrêt {i+1}")

            # Construction du contenu du client-card et address-box
            current_card_content = f'<h3 style="margin:0; color: white;">{i+1}. {type_icon} {display_name}</h3>'
            current_card_content += f'<p style="margin: 5px 0; opacity: 0.9;">'
            current_card_content += f'⌚ Arrivée estimée : <b>{arrival_time_at_client.strftime("%H:%M")}</b>'
            if wait_time_mins > 0:
                current_card_content += f'<span class="constraint-badge">Attente: {wait_time_mins:.0f}m</span>'
            current_card_content += f' | Temps sur place : {client.get("dur", 15)} min'
            if client.get('use_h', False):
                current_card_content += f' <span class="constraint-badge">Fenêtre: {client["t1"].strftime("%H:%M")}-{client["t2"].strftime("%H:%M")}</span>'
            current_card_content += '</p>'
            
            st.markdown(f'<div class="client-card">{current_card_content}</div>', unsafe_allow_html=True)
            st.markdown('<div class="address-box">', unsafe_allow_html=True)
            st.code(client['full'], language=None)
            st.markdown('</div>', unsafe_allow_html=True)

            folium.Marker([client['lat'], client['lng']], tooltip=display_name, icon=folium.Icon(color="blue")).add_to(m_final)
            
            # Ajout du segment de trajet précédent sur la carte
            if i > 0 and i-1 < len(legs):
                prev_leg_geometry = legs[i-1]['geometry']['coordinates']
                decoded_points = [(p[1], p[0]) for p in prev_leg_geometry]
                folium.PolyLine(decoded_points, color="blue", weight=5, opacity=0.7).add_to(m_final)

            current_time = arrival_time_at_client + timedelta(minutes=service_time_mins)

            # Cumul des totaux
            total_distance += leg['distance']['value']
            total_duration_minutes += adjusted_duration_mins
            total_service_time += service_time_mins
            total_wait_time += wait_time_mins

        # Ajouter le dernier segment de retour au dépôt s'il existe
        if len(legs) > len(ordered_clients): # Le dernier leg est le retour
            final_leg = legs[-1]
            total_distance += final_leg['distance']['value']
            total_duration_minutes += int((final_leg['duration']['value'] / 60) * t_mult)
            
            # Dessiner le tout dernier segment
            final_leg_geometry = final_leg['geometry']['coordinates']
            decoded_points = [(p[1], p[0]) for p in final_leg_geometry]
            folium.PolyLine(decoded_points, color="blue", weight=5, opacity=0.7).add_to(m_final)

        # Affichage des résumés (modérément stylisé)
        st.markdown("---")
        st.subheader("📊 Résumé de la tournée")
        st.markdown(f'<div style="padding: 5px 10px; border: 1px solid #ccc; border-radius: 4px; margin-bottom: 5px;">Distance totale : {total_distance/1000:.1f} km</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="padding: 5px 10px; border: 1px solid #ccc; border-radius: 4px; margin-bottom: 5px;">Durée des trajets : {total_duration_minutes:.0f} min (véhicule {st.session_state.vehicle})</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="padding: 5px 10px; border: 1px solid #ccc; border-radius: 4px; margin-bottom: 5px;">Temps total sur place (avec attentes) : {total_service_time:.0f} min</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="padding: 5px 10px; border: 1px solid #ccc; border-radius: 4px; margin-bottom: 5px;">Temps d\'attente total : {total_wait_time:.0f} min</div>', unsafe_allow_html=True)
        
        final_departure_from_depot = datetime.combine(datetime.today(), depot['h_dep'])
        total_time_spent = total_service_time + total_duration_minutes
        st.markdown(f'<div style="padding: 5px 10px; border: 1px solid #ccc; border-radius: 4px; margin-bottom: 5px;">Heure de retour estimée au dépôt : <b>{ (final_departure_from_depot + timedelta(minutes=total_time_spent)).strftime("%H:%M:%S") }</b></div>', unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("📍 Carte de l'itinéraire")
        folium_static(m_final, width=1000)

    else:
        # Affichage de l'erreur si 'legs' n'est pas présent dans la réponse
        st.error("Erreur lors du calcul de l'itinéraire. L'API Google Directions n'a pas retourné les informations nécessaires.")
        if 'res' in locals() and res and isinstance(res, list) and len(res) > 0:
            st.text(f"Réponse partielle de l'API : {res[0]}") # Affiche le début de la réponse pour debug
        else:
            st.text("Aucune réponse valide de l'API.")
        
        if st.button("⬅️ Revenir à la configuration"):
            st.session_state.step = 2
            st.rerun()
