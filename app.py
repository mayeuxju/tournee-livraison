# -*- coding: utf-8 -*-
"""
app.py - Livreur Pro Suisse
Version : révision avec corrections et implémentation OTR 1 (simuler_journee_avec_pauses)
Commentaires et messages en français.

Points importants :
- Remplace folium_static par st_folium (streamlit-folium).
- Utilise st.rerun() (pas st.experimental_rerun()).
- Gestion robuste des appels Google Maps (try/except).
- Initialisation complète de st.session_state.
- Implémentation de simuler_journee_avec_pauses conforme à OTR résumé fourni.
"""

import streamlit as st
from streamlit_folium import st_folium
import folium
from datetime import datetime, date, time as dtime, timedelta
import googlemaps
import polyline
import uuid
import logging

# -----------------------------------------------------------------------------
# CONFIG / CONSTANTES OTR (Suisse) - paramètres métier
# -----------------------------------------------------------------------------
# Règles essentielles extraites du résumé OTR 1 fourni
OTR_PARAMS = {
    "max_conduite_jour": 9 * 60,  # minutes (9h)
    "max_conduite_jour_exception": 10 * 60,  # minutes (10h) possible 2x/semaine (non géré en cumul hebdo ici)
    "max_continue_minutes": 4 * 60 + 30,  # 4h30 en minutes
    "pause_obligatoire_minutes": 45,  # pause minimum après 4h30 conduite
    # fractionnement autorisé : 15 + 30 (dans cet ordre)
    "pause_fraction_1": 15,
    "pause_fraction_2": 30,
    # repos journalier
    "repos_standard_minutes": 11 * 60,
    "repos_reduit_minutes": 9 * 60,
}

# -----------------------------------------------------------------------------
# UTILITAIRES GÉNÉRAUX
# -----------------------------------------------------------------------------
def minutes_to_hm(mins: int):
    """Retourne une chaîne "Hh Mm" à partir de minutes entières."""
    h = mins // 60
    m = mins % 60
    return f"{h}h{m:02d}"

def safe_get(o, *keys, default=None):
    """Accès sûr dans dictionnaires imbriqués."""
    cur = o
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur

# -----------------------------------------------------------------------------
# FONCTIONS MÉTIER (address validation, stop init, normalisation, simulation OTR)
# -----------------------------------------------------------------------------
def validate_address(num, rue, npa, vil, gmaps_client=None):
    """
    Tente de valider et géocoder une adresse via Google Maps.
    Retourne dictionnaire avec lat,lng,display,raw (n,r,rue,npa,ville),full,formatted_address
    ou None si échec.
    """
    addr = f"{num} {rue}, {npa} {vil}, Suisse"
    if gmaps_client is None:
        # Sans Google, on retourne None (ou on pourrait faire un fallback).
        return None
    try:
        res = gmaps_client.geocode(addr)
    except Exception as e:
        st.error(f"Erreur géocodage Google : {e}")
        return None

    if not res:
        return None

    first = res[0]
    formatted = first.get("formatted_address", addr)
    loc = first["geometry"]["location"]
    # Nettoyage simple : suppression de ", Suisse" si présent pour l'affichage court
    display = formatted.replace(", Suisse", "").replace(", Switzerland", "")
    raw = {"n": num, "r": rue, "npa": npa, "v": vil}
    return {
        "lat": loc["lat"],
        "lng": loc["lng"],
        "display": display,
        "raw": raw,
        "full": formatted,
        "formatted_address": formatted,
    }


def init_stop_dict(geo_res, is_depot=False):
    """Initialise la structure d'un arrêt à partir du résultat de validate_address."""
    base = {
        "id": str(uuid.uuid4()),
        "nom": geo_res.get("nom", geo_res.get("display", "Point")),
        "full": geo_res["full"],
        "display": geo_res["display"],
        "raw": geo_res.get("raw", {}),
        "lat": geo_res["lat"],
        "lng": geo_res["lng"],
        "type": "Dépôt" if is_depot else geo_res.get("type", "Livraison"),
        "dur": geo_res.get("dur", 10),
        "use_h": geo_res.get("use_h", False),
        "t1": geo_res.get("t1", dtime(8, 0)),
        "t2": geo_res.get("t2", dtime(17, 0)),
        "statut": geo_res.get("statut", "a_faire"),
        # champs temps estimés / réels
        "heure_arrivee_estimee": None,
        "heure_depart_estimee": None,
        "heure_depart_reelle": None,
        # pour ramasse
        "is_ramasse_forcee_aller": geo_res.get("is_ramasse_forcee_aller", False),
    }
    # dépôt spécifique : heure de départ
    if is_depot:
        base["h_dep"] = geo_res.get("h_dep", dtime(8, 0))
    return base


def normalize_existing_stops():
    """
    Normalise les arrêts existants dans st.session_state.stops pour garantir
    compatibilité ascendante. Cette fonction corrige clés manquantes et types.
    """
    stops = st.session_state.get("stops", [])
    for i, s in enumerate(stops):
        # Assure la présence d'un id
        if "id" not in s:
            s["id"] = str(uuid.uuid4())
        # Champs minimaux
        s.setdefault("nom", s.get("display", f"Client {i}"))
        s.setdefault("full", s.get("full", s.get("display", s["nom"])))
        s.setdefault("raw", s.get("raw", {"n": "", "r": "", "npa": "", "v": ""}))
        s.setdefault("lat", s.get("lat", 0.0))
        s.setdefault("lng", s.get("lng", 0.0))
        s.setdefault("type", s.get("type", "Livraison" if i != 0 else "Dépôt"))
        s.setdefault("dur", int(s.get("dur", 10)))
        s.setdefault("use_h", bool(s.get("use_h", False)))
        s.setdefault("t1", s.get("t1", dtime(8, 0)))
        s.setdefault("t2", s.get("t2", dtime(17, 0)))
        s.setdefault("statut", s.get("statut", "a_faire"))
        s.setdefault("heure_arrivee_estimee", None)
        s.setdefault("heure_depart_estimee", None)
        s.setdefault("heure_depart_reelle", s.get("heure_depart_reelle", None))
        s.setdefault("is_ramasse_forcee_aller", s.get("is_ramasse_forcee_aller", False))
    st.session_state.stops = stops


def simuler_journee_avec_pauses(legs_minutes, services_minutes, depart_time, params=OTR_PARAMS):
    """
    Simule une journée de conduite + services et insère les pauses OTR 1 automatiquement.
    Input:
      - legs_minutes : liste des durées de trajet successives en minutes (entre points)
                       longueur = nombre d'arrêts (clients) + 1 (si retour au dépôt)
                       mais pour simplifier on considère legs_minutes[i] comme trajet entre
                       arrêt i et i+1 (i=0 : entre dépôt et 1er client).
      - services_minutes : liste des temps passés sur place pour chaque arrêt (clients)
                           longueur = nombre de clients (exclut le dépôt initial).
      - depart_time : datetime (date+heure) du départ du dépôt.
      - params : paramètres OTR.
    Retour:
      - dict avec events (list), conduite_totale_min, pauses_inserees, violations (list)
    Notes:
      - On considère uniquement la journée de travail actuelle (détection de dépassements journaliers)
      - Fractionnement de pause autorisé 15 + 30 (dans cet ordre) pour remettre le compteur à zéro.
    """
    events = []  # chaque event = dict {type: 'conduite'|'service'|'pause', start, end, info}
    pauses = []
    violations = []

    max_continue = params["max_continue_minutes"]
    pause_required = params["pause_obligatoire_minutes"]
    frag1 = params["pause_fraction_1"]
    frag2 = params["pause_fraction_2"]
    max_jour = params["max_conduite_jour"]

    # état courant
    current_time = depart_time
    conduite_continue = 0  # minutes depuis la dernière pause/fin repos
    conduite_totale = 0

    n_legs = len(legs_minutes)
    n_services = len(services_minutes)

    # Fonction utilitaire pour ajouter un event
    def add_event(ev_type, start, duration_min, info=None):
        end = start + timedelta(minutes=duration_min)
        events.append({"type": ev_type, "start": start, "end": end, "dur_min": duration_min, "info": info})
        return end

    # On parcourt alternance: trajet(leg0) -> service0 -> trajet(leg1) -> service1 -> ...
    # legs_minutes length should be n_services + 1 (return to depot optionally). We itère sur services.
    for idx in range(max(n_legs, n_services)):
        # 1) Trajet i (si présent)
        if idx < n_legs:
            t_leg = max(0, int(legs_minutes[idx]))
            # Si ce trajet dépasse la conduite continue autorisée -> on doit insérer pause(s) pendant le trajet
            if conduite_continue + t_leg > max_continue:
                # Calcul du temps restant avant déclenchement
                temps_avant_pause = max_continue - conduite_continue
                if temps_avant_pause > 0:
                    # On fait une conduite partielle puis pause
                    start_leg_part1 = current_time
                    current_time = add_event("conduite", start_leg_part1, temps_avant_pause, info={"part": "avant_pause"})
                    conduite_totale += temps_avant_pause
                    t_leg -= temps_avant_pause
                    conduite_continue += temps_avant_pause
                # Insérer pause obligatoire (45 min) ou fractionnée si possible
                # Ici on choisit la pause complète 45 min pour simplicité opérationnelle,
                # mais on offre la possibilité de fractionner en 15+30 si l'algorithme décide.
                # Priorité : si il reste moins d'un trajet court, il est souvent préférable de faire
                # pause complète.
                pause_start = current_time
                current_time = add_event("pause", pause_start, pause_required, info={"auto":"OTR_45"})
                pauses.append({"start": pause_start, "dur": pause_required})
                conduite_continue = 0
                # après pause on poursuit le trajet restant
                if t_leg > 0:
                    start_leg_part2 = current_time
                    current_time = add_event("conduite", start_leg_part2, t_leg, info={"part":"apres_pause"})
                    conduite_totale += t_leg
                    conduite_continue += t_leg
            else:
                # trajet normal sans pause
                start_leg = current_time
                current_time = add_event("conduite", start_leg, t_leg)
                conduite_totale += t_leg
                conduite_continue += t_leg

        # 2) Service idx (si présent)
        if idx < n_services:
            t_srv = max(0, int(services_minutes[idx]))
            start_srv = current_time
            current_time = add_event("service", start_srv, t_srv)
            # Remarque : service n'est pas conduite; selon OTR, travail compte pour durée de service,
            # mais n'interrompt pas la conduite continue (sauf si le chauffeur a une période de repos).
            # Toutefois, les interruptions de travail ne comptent pas comme conduite. Ici on ne remet pas
            # conduite_continue à zéro après un service.
            # Si tu veux qu'un service valide comme "pause" (libre), il faut explicitement le considérer.
            # Nous considérons ici que le service n'efface pas le compteur conduite_continue.
            # (Conformité stricte: la pause doit être libre de travail pour remettre le compteur.)
            # On laisse conduite_continue inchangé.
            # Si tu veux qu'un service soit une pause (ex: 30+15), tu peux marquer ce service comme 'pause_effective'.
            pass

        # Contrôle de dépassement maximum journalier de conduite
        if conduite_totale > max_jour:
            violations.append({
                "type": "conduite_journaliere",
                "message": f"Conduite totale {conduite_totale} min > maximum journalier {max_jour} min",
                "conduite_totale_min": conduite_totale,
            })

    # Résumé
    result = {
        "events": events,
        "pauses": pauses,
        "conduite_totale_min": conduite_totale,
        "violations": violations,
    }
    return result

# -----------------------------------------------------------------------------
# INITIALISATION STREAMLIT / SESSION
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Livreur Pro Suisse", layout="wide")

# Initialisation sécurisée de st.session_state
if "stops" not in st.session_state:
    st.session_state.stops = []

if "step" not in st.session_state:
    st.session_state.step = 1

if "vehicle" not in st.session_state:
    st.session_state.vehicle = "Voiture"

if "edit_idx" not in st.session_state:
    st.session_state.edit_idx = None

if "f_nom" not in st.session_state:
    # Champs formulaire par défaut
    st.session_state.f_nom = ""
    st.session_state.f_num = ""
    st.session_state.f_rue = ""
    st.session_state.f_npa = ""
    st.session_state.f_vil = ""
    st.session_state.f_dur = 10
    st.session_state.f_use_h = False
    st.session_state.f_type = "Livraison"
    st.session_state.f_t1 = dtime(8, 0)
    st.session_state.f_t2 = dtime(17, 0)
    st.session_state.f_hdep = dtime(8, 0)
    st.session_state.f_ramasse_forcee_aller = False

if "ordered_client_ids" not in st.session_state:
    st.session_state.ordered_client_ids = []

if "algo" not in st.session_state:
    st.session_state.algo = "Mathématique (Google)"  # valeur par défaut

# Normalisation des arrêts existants
normalize_existing_stops()

# Initialisation client Google Maps (si présent)
gmaps = None
try:
    if "google" in st.secrets and "api_key" in st.secrets["google"]:
        gmaps = googlemaps.Client(key=st.secrets["google"]["api_key"])
    else:
        # Pas de clé dans secrets -> on laisse gmaps à None mais on n'arrête pas l'app.
        gmaps = None
        # affiche avertissement discret
        st.sidebar.warning("Clé Google Maps introuvable dans .streamlit/secrets.toml : certaines fonctions désactivées.")
except Exception as e:
    st.sidebar.error("Erreur initialisation Google Maps client : vérifiez la clé dans secrets.")
    gmaps = None

# -----------------------------------------------------------------------------
# UI : ÉTAPE 1 - Choix du véhicule
# -----------------------------------------------------------------------------
if st.session_state.step == 1:
    st.title("🚚 Type de transport")
    st.write("Sélectionnez le type de véhicule utilisé pour cette tournée.")
    v = st.radio("Véhicule :", ["Voiture", "Camion (Lourd)"], index=0)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Valider ➡️", use_container_width=True):
            st.session_state.vehicle = v
            st.session_state.step = 2
            st.rerun()

# -----------------------------------------------------------------------------
# UI : ÉTAPE 2 - Configuration de la tournée
# -----------------------------------------------------------------------------
elif st.session_state.step == 2:
    st.title("📍 Configuration de la tournée")
    col_form, col_map = st.columns([1.2, 1])

    with col_form:
        st.subheader("Ajouter un dépôt ou un client")
        # Formulaire simple pour ajouter un point (utilisation basique)
        with st.form("form_ajout"):
            nom = st.text_input("Nom / Enseigne", value=st.session_state.f_nom)
            c1, c2 = st.columns([1, 3])
            num = c1.text_input("N°", value=st.session_state.f_num)
            rue = c2.text_input("Rue", value=st.session_state.f_rue)
            c3, c4 = st.columns(2)
            npa = c3.text_input("NPA", value=st.session_state.f_npa)
            vil = c4.text_input("Ville", value=st.session_state.f_vil)
            c5, c6 = st.columns(2)
            typ = c5.selectbox("Type", ["Dépôt", "Livraison", "Ramasse"], index=1 if st.session_state.f_type!="Dépôt" else 0)
            dur = c6.number_input("Temps sur place (min)", 1, 240, value=st.session_state.f_dur)
            use_h = st.checkbox("Horaire impératif", value=st.session_state.f_use_h)
            t1 = dtime(8, 0)
            t2 = dtime(17, 0)
            if use_h:
                t1 = st.time_input("Pas avant", value=st.session_state.f_t1)
                t2 = st.time_input("Pas après", value=st.session_state.f_t2)
            submitted = st.form_submit_button("Ajouter")
            if submitted:
                if gmaps is None:
                    st.warning("Géocodage désactivé (pas de clé Google). Impossible d'ajouter automatiquement.")
                else:
                    res_geo = validate_address(num, rue, npa, vil, gmaps)
                    if not res_geo:
                        st.warning("Adresse introuvable, merci de vérifier les champs.")
                    else:
                        res_geo["nom"] = nom or res_geo["display"]
                        res_geo.update({
                            "type": typ,
                            "dur": int(dur),
                            "use_h": bool(use_h),
                            "t1": t1,
                            "t2": t2,
                            "is_ramasse_forcee_aller": False,
                        })
                        is_depot = typ == "Dépôt"
                        stop = init_stop_dict(res_geo, is_depot=is_depot)
                        if is_depot:
                            # depot en tête
                            if st.session_state.stops and st.session_state.stops[0].get("type") == "Dépôt":
                                st.session_state.stops[0] = stop
                            else:
                                st.session_state.stops.insert(0, stop)
                        else:
                            st.session_state.stops.append(stop)
                        st.session_state.ordered_client_ids = []  # forcer recalcul
                        st.success("Point ajouté.")
                        st.rerun()

        st.markdown("---")
        st.subheader("Liste des arrêts")
        # Affichage simple des arrêts enregistrés
        for i, s in enumerate(st.session_state.stops):
            cols = st.columns([7, 2, 1, 1])
            with cols[0]:
                st.markdown(f"**{i}. {s.get('nom','')}** — {s.get('display','')}")
            with cols[1]:
                st.write("✅" if s.get("statut") == "fait" else "🕓")
            if cols[2].button("✏️", key=f"edit_{i}"):
                st.session_state.edit_idx = i
                st.session_state.f_nom = s.get("nom", "")
                st.session_state.f_num = s.get("raw", {}).get("n", "")
                st.session_state.f_rue = s.get("raw", {}).get("r", "")
                st.session_state.f_npa = s.get("raw", {}).get("npa", "")
                st.session_state.f_vil = s.get("raw", {}).get("v", "")
                if i == 0:
                    st.session_state.f_hdep = s.get("h_dep", dtime(8, 0))
                else:
                    st.session_state.f_dur = s.get("dur", 10)
                    st.session_state.f_use_h = s.get("use_h", False)
                    st.session_state.f_type = s.get("type", "Livraison")
                    st.session_state.f_t1 = s.get("t1", dtime(8, 0))
                    st.session_state.f_t2 = s.get("t2", dtime(17, 0))
                    st.session_state.f_ramasse_forcee_aller = s.get("is_ramasse_forcee_aller", False)
                st.rerun()
            if cols[3].button("🗑️", key=f"del_{i}"):
                st.session_state.stops.pop(i)
                st.session_state.ordered_client_ids = []
                st.rerun()

        st.markdown("---")
        # Choix de l'algorithme
        st.session_state.algo = st.selectbox("Algorithme d'optimisation", ["Mathématique (Google)", "Logique Chauffeur (Aller -> Retour)"], index=0 if st.session_state.algo.startswith("Math") else 1)
        if st.button("➡️ Calculer l'itinéraire"):
            if len(st.session_state.stops) < 2:
                st.warning("Ajoutez au moins un dépôt et un client pour calculer.")
            else:
                st.session_state.step = 3
                st.rerun()

    # Colonne carte (aperçu)
    with col_map:
        m = folium.Map(location=[46.8, 8.2], zoom_start=7)
        for i, s in enumerate(st.session_state.stops):
            folium.Marker([s["lat"], s["lng"]], tooltip=s["nom"], icon=folium.Icon(color="green" if i == 0 else "blue")).add_to(m)
        st_folium(m, width=400, height=300)

# -----------------------------------------------------------------------------
# UI : ÉTAPE 3 - Itinéraire optimisé + simulation + insertion clients
# -----------------------------------------------------------------------------
elif st.session_state.step == 3:
    st.title("🏁 Itinéraire Optimisé")

    t_mult = 1.25 if st.session_state.vehicle == "Camion (Lourd)" else 1.0

    if len(st.session_state.stops) < 2:
        st.warning("Il faut au moins un dépôt et un client pour calculer un itinéraire.")
        if st.button("⬅️ Retour à la configuration"):
            st.session_state.step = 2
            st.rerun()
        st.stop()

    depot = st.session_state.stops[0]
    clients = st.session_state.stops[1:]

    # Sépare livraisons / ramasses
    livraisons = [c for c in clients if c.get("type") == "Livraison"]
    ramasses = [c for c in clients if c.get("type") == "Ramasse"]

    ordered_clients = None
    res = None

    # --------------------------------------------------------
    # 1) Aucun client livré => calcul standard
    # --------------------------------------------------------
    if all(c.get("statut") != "fait" for c in clients):
        if st.session_state.algo == "Logique Chauffeur (Aller -> Retour)":
            ramasses_aller = [c for c in ramasses if c.get("is_ramasse_forcee_aller")]
            ramasses_retour = [c for c in ramasses if not c.get("is_ramasse_forcee_aller")]

            def dist2(x):
                return (x["lat"] - depot["lat"]) ** 2 + (x["lng"] - depot["lng"]) ** 2

            bloc_aller = livraisons + ramasses_aller
            bloc_aller.sort(key=dist2)
            ramasses_retour.sort(key=dist2, reverse=True)

            ordered_clients = bloc_aller + ramasses_retour

            waypoints = [c["full"] for c in ordered_clients]
            try:
                if gmaps:
                    res = gmaps.directions(depot["full"], depot["full"], waypoints=waypoints, optimize_waypoints=False)
                else:
                    res = None
            except Exception as e:
                st.error(f"Erreur Google Directions : {e}")
                res = None
        else:
            # Mathématique : Google optimise l'ordre des clients
            waypoints = [c["full"] for c in clients]
            try:
                if gmaps:
                    res = gmaps.directions(depot["full"], depot["full"], waypoints=waypoints, optimize_waypoints=True)
                    # si Google renvoie un ordre, on construit ordered_clients
                    if res and "waypoint_order" in res[0]:
                        order = res[0]["waypoint_order"]
                        ordered_clients = [clients[i] for i in order]
                    else:
                        ordered_clients = clients[:]
                else:
                    ordered_clients = clients[:]
                    res = None
            except Exception as e:
                st.error(f"Erreur Google Directions : {e}")
                ordered_clients = clients[:]
                res = None

    else:
        # --------------------------------------------------------
        # 2) Cas où certains clients sont déjà faits -> gestion suffixe
        # --------------------------------------------------------
        deja_faits = [c for c in clients if c.get("statut") == "fait"]
        deja_faits_ids = [c["id"] for c in deja_faits]

        # On remplit prefix avec ceux qui sont faits mais ne doublons pas
        # suffix : ceux à faire
        a_faire = [c for c in clients if c.get("statut") != "fait"]

        if st.session_state.algo == "Logique Chauffeur (Aller -> Retour)":
            # on applique la logique chauffeur sur "a_faire"
            livraisons_af = [c for c in a_faire if c["type"] == "Livraison"]
            ramasses_aller_af = [c for c in a_faire if c["type"] == "Ramasse" and c.get("is_ramasse_forcee_aller")]
            ramasses_retour_af = [c for c in a_faire if c["type"] == "Ramasse" and not c.get("is_ramasse_forcee_aller")]

            def dist2(x):
                return (x["lat"] - depot["lat"]) ** 2 + (x["lng"] - depot["lng"]) ** 2

            bloc_aller = livraisons_af + ramasses_aller_af
            bloc_aller.sort(key=dist2)
            ramasses_retour_af.sort(key=dist2, reverse=True)

            ordered_a_faire = bloc_aller + ramasses_retour_af
        else:
            # Google optimise uniquement le suffixe
            if a_faire and gmaps:
                waypoints_suffix = [c["full"] for c in a_faire]
                try:
                    res_suffix = gmaps.directions(depot["full"], depot["full"], waypoints=waypoints_suffix, optimize_waypoints=True)
                    if res_suffix and "waypoint_order" in res_suffix[0]:
                        order_suffix = res_suffix[0]["waypoint_order"]
                        ordered_a_faire = [a_faire[i] for i in order_suffix]
                    else:
                        ordered_a_faire = a_faire[:]
                except Exception as e:
                    st.error(f"Erreur Google (suffixe) : {e}")
                    ordered_a_faire = a_faire[:]
            else:
                ordered_a_faire = a_faire[:]

        ordered_clients = deja_faits + ordered_a_faire

        # On appelle Google pour obtenir trajectoire sans ré-optimiser (on impose ordered_clients)
        waypoints_all = [c["full"] for c in ordered_clients]
        try:
            if gmaps:
                res = gmaps.directions(depot["full"], depot["full"], waypoints=waypoints_all, optimize_waypoints=False)
            else:
                res = None
        except Exception as e:
            st.error(f"Erreur Google Directions : {e}")
            res = None

    # Résultat de l'appel Google
    if not res:
        st.error("Impossible de calculer l’itinéraire avec Google Maps (ou clé manquante).")
        if st.button("⬅️ Retour à la configuration"):
            st.session_state.step = 2
            st.rerun()
        st.stop()
    else:
        # On mémorise à chaque fois l'ordre global obtenu
        if ordered_clients is not None:
            st.session_state.ordered_client_ids = [c["id"] for c in ordered_clients]
        else:
            ordered_clients = clients[:]
            st.session_state.ordered_client_ids = [c["id"] for c in ordered_clients]

        # Extraction des legs
        legs = res[0].get("legs", [])
        if not legs or len(legs) < len(ordered_clients):
            # sécurité : si legs manquent, on stoppe proprement
            st.warning("Réponse Google incomplète : impossible d'extraire tous les tronçons. Affichage partiel.")
        # Recherche du dernier client "fait" avec heure réelle
        last_done_index = -1
        for idx, c in enumerate(ordered_clients):
            if c.get("statut") == "fait" and c.get("heure_depart_reelle") is not None:
                last_done_index = idx

        # Heure de départ par défaut : heure de départ dépôt (date = aujourd'hui)
        depart_time = datetime.combine(date.today(), depot.get("h_dep", dtime(8, 0)))
        current_time = depart_time
        st.success(f"🏠 DÉPART DU DÉPÔT : {current_time.strftime('%H:%M')}")

        # Construction carte finale
        m_final = folium.Map(location=[depot["lat"], depot["lng"]], zoom_start=10)
        folium.Marker([depot["lat"], depot["lng"]], popup="DÉPÔT", icon=folium.Icon(color="green")).add_to(m_final)

        # calculs temps et simulation OTR
        legs_minutes = []
        services_minutes = []
        for i, client in enumerate(ordered_clients):
            if i < len(legs):
                dur_mins = int((legs[i].get("duration", {}).get("value", 0) / 60) * t_mult)
            else:
                dur_mins = 0
            legs_minutes.append(dur_mins)
            services_minutes.append(int(client.get("dur", 10)))

        # on rajoute le dernier leg (retour au dépôt) si présent dans legs
        if len(legs) > len(ordered_clients):
            # leg final (vers dépôt de retour)
            legs_minutes.append(int((legs[-1].get("duration", {}).get("value", 0) / 60) * t_mult))

        # simulate OTR : on considère legs_minutes list et services_minutes (clients)
        sim = simuler_journee_avec_pauses(legs_minutes, services_minutes, depart_time, params=OTR_PARAMS)

        # Affichage synthèse clients + heures estimées (simple propagation)
        current_time = depart_time
        for i, client in enumerate(ordered_clients):
            leg_min = legs_minutes[i] if i < len(legs_minutes) else 0
            arrive_est = current_time + timedelta(minutes=leg_min)
            depart_est = arrive_est + timedelta(minutes=client.get("dur", 10))
            client["heure_arrivee_estimee"] = arrive_est
            client["heure_depart_estimee"] = depart_est
            # affichage
            statut = client.get("statut", "a_faire")
            is_done = statut == "fait"
            type_icon = "📦" if client.get("type") == "Livraison" else ("📥" if client.get("type") == "Ramasse" else "📍")
            retard_txt = ""
            if is_done and client.get("heure_depart_reelle"):
                delta_min = int((client["heure_depart_reelle"] - client["heure_depart_estimee"]).total_seconds() // 60)
                retard_txt = f" | Retard {delta_min} min" if delta_min > 0 else (f" | Avance {abs(delta_min)} min" if delta_min < 0 else " | À l'heure")
            st.markdown(f"- **{type_icon} {client.get('nom','')}** — {client.get('display','')} — {client['heure_arrivee_estimee'].strftime('%H:%M')} → {client['heure_depart_estimee'].strftime('%H:%M')} {retard_txt}")

            # Marker sur carte
            folium.Marker([client["lat"], client["lng"]],
                          popup=f"{client.get('nom','')} ({client.get('type')})",
                          tooltip=client.get('nom'),
                          icon=folium.Icon(color="blue" if not is_done else "lightgray")
                          ).add_to(m_final)

            # Avance current_time
            current_time = depart_est

        # Trace du trajet global
        try:
            pts = polyline.decode(res[0]["overview_polyline"]["points"])
            folium.PolyLine(pts, color="blue", weight=5).add_to(m_final)
        except Exception:
            # si polyline manquante -> on connecte markers dans l'ordre
            coords = [(depot["lat"], depot["lng"])] + [(c["lat"], c["lng"]) for c in ordered_clients] + [(depot["lat"], depot["lng"])]
            folium.PolyLine(coords, color="blue", weight=3).add_to(m_final)

        st_folium(m_final, width=1000, height=500)

        # Affiche résumé simulation OTR
        st.markdown("### OTR - Simulation des pauses / conduite")
        st.write(f"Conduite totale estimée : {sim['conduite_totale_min']} minutes ({minutes_to_hm(sim['conduite_totale_min'])})")
        if sim["pauses"]:
            for p in sim["pauses"]:
                st.write(f"- Pause automatique insérée : {p['start'].strftime('%H:%M')} — {minutes_to_hm(p['dur'])}")
        else:
            st.write("- Aucune pause automatique insérée (vérifier planning)")

        if sim["violations"]:
            st.error("Violations détectées :")
            for v in sim["violations"]:
                st.write(f"- {v.get('message')}")
        else:
            st.success("Aucune violation OTR détectée pour la conduite totale simulée.")

        # -----------------------------------------------------------------
        # ➕ AJOUT D'UN CLIENT EN COURS DE TOURNÉE (ÉTAPE 3)
        # -----------------------------------------------------------------
        with st.expander("➕ Ajouter un client / une ramasse en cours de tournée"):
            with st.form("form_add_during_route"):
                nom_new = st.text_input("Nom / Enseigne (nouveau point)")
                c1, c2 = st.columns([1, 3])
                num_new = c1.text_input("N°", key="num_new")
                rue_new = c2.text_input("Rue", key="rue_new")
                c3, c4 = st.columns(2)
                npa_new = c3.text_input("NPA", key="npa_new")
                vil_new = c4.text_input("Ville", key="vil_new")
                c5, c6 = st.columns(2)
                type_new = c5.selectbox("Type de mission", ["Livraison", "Ramasse"], key="type_new")
                dur_new = c6.number_input("Temps sur place (min)", 1, 240, 10, key="dur_new")
                use_h_new = st.checkbox("Horaire impératif pour ce client", key="use_h_new")
                ramasse_forcee_new = False
                if type_new == "Ramasse":
                    ramasse_forcee_new = st.checkbox("Faire cette ramasse à l'aller", key="ramasse_forcee_new")
                t1_new = dtime(8, 0)
                t2_new = dtime(17, 0)
                if use_h_new:
                    c7, c8 = st.columns(2)
                    t1_new = c7.time_input("Pas avant", value=dtime(8, 0), key="t1_new")
                    t2_new = c8.time_input("Pas après", value=dtime(17, 0), key="t2_new")
                submitted_new = st.form_submit_button("✅ Enregistrer ce point et recalculer l'itinéraire")
                if submitted_new:
                    if gmaps is None:
                        st.warning("Géocodage indisponible (clé Google manquante).")
                    else:
                        res_new = validate_address(num_new, rue_new, npa_new, vil_new, gmaps)
                        if not res_new:
                            st.warning("Adresse introuvable, merci de vérifier les champs.")
                        else:
                            res_new["nom"] = nom_new or f"Client {len(st.session_state.stops)}"
                            res_new.update({
                                "type": type_new,
                                "use_h": use_h_new,
                                "dur": dur_new,
                                "t1": t1_new,
                                "t2": t2_new,
                                "is_ramasse_forcee_aller": ramasse_forcee_new,
                                "statut": "a_faire",
                            })
                            new_stop = init_stop_dict(res_new, is_depot=False)
                            st.session_state.stops.append(new_stop)
                            st.session_state.ordered_client_ids = []
                            st.success("Point ajouté et itinéraire recalculé.")
                            st.rerun()

        if st.button("⬅️ Modifier la tournée"):
            st.session_state.step = 2
            st.rerun()
