from flask import Flask, render_template, request, jsonify
import requests
from math import radians, sin, cos, sqrt, atan2

# Initialisation de l'application Flask
app = Flask(__name__)

# Configuration des clés API et URLs pour GraphHopper et Chargetrip
GRAPHOPPER_API_KEY = '1395718d-379c-452b-b1c7-538e1a5a7a68'
GRAPHOPPER_URL = "https://graphhopper.com/api/1/route"
CHARGETRIP_CLIENT_KEY = '6710ba84021ae871189270f5'
CHARGETRIP_APP_KEY = '6710ba84021ae871189270f7'
CHARGETRIP_URL = 'https://api.chargetrip.io/graphql'

# Variable globale pour stocker les données des véhicules
vehicles_data = []

# Requête GraphQL pour récupérer les données de tous les véhicules
graphql_query_vehicles = """
query vehicleListAll {
  vehicleList {
    id
    naming {
      make
      model
      version
      edition
      chargetrip_version
    }
    drivetrain {
      type
    }
    connectors {
      standard
      power
      max_electric_power
      time
      speed
    }
    battery {
      usable_kwh
      full_kwh
    }
    range {
      chargetrip_range {
        best
        worst
      }
    }
  }
}
"""

def fetch_vehicles_data():
    """
    Fonction pour récupérer les données des véhicules depuis l'API Chargetrip
    et les stocker dans la variable globale `vehicles_data`.
    """
    global vehicles_data
    headers = {
        'x-client-id': CHARGETRIP_CLIENT_KEY,
        'x-app-id': CHARGETRIP_APP_KEY,
        'Authorization': f'Bearer {CHARGETRIP_CLIENT_KEY}',
        'Content-Type': 'application/json'
    }
    try:
        response = requests.post(CHARGETRIP_URL, json={'query': graphql_query_vehicles}, headers=headers)
        response.raise_for_status()
        vehicles_data = response.json().get('data', {}).get('vehicleList', [])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching vehicles data: {e}")
        vehicles_data = []

@app.route('/')
def index():
    """
    Route principale pour afficher la page d'accueil avec la liste des véhicules.
    """
    try:
        fetch_vehicles_data()  # Récupération des données des véhicules
        return render_template('index.html', vehicles=vehicles_data)
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/route_data', methods=['POST'])
def route_data():
    """
    Route pour traiter les demandes de données d'itinéraire en fonction
    des villes de départ et d'arrivée, et du véhicule sélectionné.
    """
    ville_depart = request.form['start_city']
    ville_arrivee = request.form['end_city']
    vehicule_id = request.form['vehicle_id']

    try:
        # Récupération des informations du véhicule sélectionné
        vehicle_data = next((v for v in vehicles_data if v['id'] == vehicule_id), None)
        
        if not vehicle_data:
            return jsonify({'error': 'Vehicle not found'}), 404

        # Détails du véhicule pour affichage
        vehicle_details = {
            'make': vehicle_data['naming']['make'],
            'model': vehicle_data['naming']['model'],
            'version': vehicle_data['naming']['version'],
            'battery_capacity': vehicle_data['battery']['usable_kwh'],
            'range': vehicle_data['range']['chargetrip_range']['best'],
            'consumption': vehicle_data['battery']['usable_kwh'] / vehicle_data['range']['chargetrip_range']['best']
        }

        # Récupération des coordonnées des villes de départ et d'arrivée
        coords_depart = get_coordinates(ville_depart)
        coords_arrivee = get_coordinates(ville_arrivee)

        if not coords_depart or not coords_arrivee:
            return jsonify({'error': 'Invalid coordinates'}), 400

        # Construction de la requête pour obtenir l'itinéraire
        params = {
            'point': [f"{coords_depart['lat']},{coords_depart['lng']}", f"{coords_arrivee['lat']},{coords_arrivee['lng']}"],
            'vehicle': 'car',
            'key': GRAPHOPPER_API_KEY,
            'instructions': 'false',
            'points_encoded': 'false'
        }
        response = requests.get(GRAPHOPPER_URL, params=params)
        response.raise_for_status()

        # Récupération des données d'itinéraire
        route_data = response.json()
        coords_itineraire = parse_coordinates(route_data)

        # Recherche des stations de recharge le long de l'itinéraire
        stations = find_charging_stations(coords_itineraire, 200, vehicle_details['consumption'], vehicle_data)

        # Ajout des points de recharge à la requête d'itinéraire
        via_points = [f"{station['location']['coordinates'][1]},{station['location']['coordinates'][0]}" for station in stations]
        if via_points:
            params['point'] = [f"{coords_depart['lat']},{coords_depart['lng']}"] + via_points + [f"{coords_arrivee['lat']},{coords_arrivee['lng']}"]

        response = requests.get(GRAPHOPPER_URL, params=params)
        response.raise_for_status()

        # Calcul de la durée totale de l'itinéraire
        route_data_with_stops = response.json()
        coords_itineraire = parse_coordinates(route_data_with_stops)
        duration_ms = route_data_with_stops['paths'][0]['time']
        hours = duration_ms // 3600000
        minutes = (duration_ms % 3600000) // 60000

        return jsonify({
            'distance': f"{route_data_with_stops['paths'][0]['distance'] / 1000:.2f} km",
            'duration': f"{hours}h {minutes}m",
            'route': coords_itineraire,
            'stations': stations,
            'vehicle_details': vehicle_details  # Détails du véhicule
        })
    except Exception as e:
        return jsonify({'error': str(e)})

def get_coordinates(city):
    """
    Fonction pour obtenir les coordonnées d'une ville en utilisant l'API GraphHopper.
    """
    response = requests.get(f"https://graphhopper.com/api/1/geocode?q={city}&key={GRAPHOPPER_API_KEY}")
    if response.status_code == 200:
        data = response.json()
        if data['hits']:
            return data['hits'][0]['point']
    return None

def parse_coordinates(route_data):
    """
    Fonction pour extraire et formater les coordonnées de l'itinéraire.
    """
    return [[coord[1], coord[0]] for coord in route_data['paths'][0]['points']['coordinates']]

def find_charging_stations(itinerary, distance_between_stations, consumption_per_km, vehicle_data):
    """
    Fonction pour trouver les stations de recharge sur l'itinéraire en fonction
    de l'autonomie "worst" du véhicule.
    """
    worst_range = vehicle_data['range']['chargetrip_range']['worst']
    stations = []
    current_distance = 0
    headers = {
        'x-client-id': CHARGETRIP_CLIENT_KEY,
        'x-app-id': CHARGETRIP_APP_KEY,
        'Authorization': f'Bearer {CHARGETRIP_CLIENT_KEY}',
        'Content-Type': 'application/json'
    }

    for i in range(len(itinerary) - 1):
        segment_distance = haversine_distance(itinerary[i], itinerary[i + 1])
        current_distance += segment_distance

        # Ajouter une station si la distance dépasse l'autonomie "worst"
        if current_distance >= worst_range:
            station_location = itinerary[i]
            query = f"""
            query {{
                stationAround(
                    filter: {{
                        location: {{ type: Point, coordinates: [{station_location[1]}, {station_location[0]}] }},
                        distance: 5000
                    }},
                    size: 1
                ) {{
                    id
                    name
                    location {{
                        coordinates
                    }}
                    power
                }}
            }}
            """
            response = requests.post(CHARGETRIP_URL, json={'query': query}, headers=headers)
            if response.status_code == 200:
                station_data = response.json().get('data', {}).get('stationAround', [])
                if station_data:
                    stations.append(station_data[0])
                    current_distance = 0  # Réinitialiser la distance après recharge

    return stations

def haversine_distance(coord1, coord2):
    """
    Fonction pour calculer la distance entre deux points en km avec la formule de Haversine.
    """
    R = 6371  # Rayon de la Terre en km
    dlat = radians(coord2[0] - coord1[0])
    dlon = radians(coord2[1] - coord1[1])
    a = sin(dlat / 2)**2 + cos(radians(coord1[0])) * cos(radians(coord2[0])) * sin(dlon / 2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

# Exécuter l'application Flask
if __name__ == '__main__':
    app.run(debug=True)
