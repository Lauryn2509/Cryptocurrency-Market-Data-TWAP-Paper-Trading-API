# Cryptocurrency-Market-Data-TWAP-Paper-Trading-API
The system is designed to simulate order execution against real market conditions without placing actual trades, allowing traders to test and refine TWAP strategies.

# A faire/ Sujet 
First implement the market data collection system
Add the TWAP execution engine
Implement the REST API endpoints
Add the WebSocket feed
Create the client implementation
Add authentication

# Notes sur la partie 1 
Petits commentaires pour comprenre le code actuel. 

Une API ça permet d’aller interroger des sites et de récupérer des données sur ceux-là. 
Les requêtes à inclure absolument 
- get
- post
- delete 

La méthode GET : son but c’est de récupérer les données
POST : potser/ajouter des données
DELETE : les supprimer

Dans notre code, on va partir de la main pour expliquer ce qu’il se passe : 

On a collect_order_book_data, une f° qui prend en arguments:
-  exchange = la plateforme sur laquelle on récupère les données*
- symbol = les symboles des cryptos qu’on veut récupérer

*à l’heure actuelle du code, pas véritablement relié au plateformes, ça sce sera dans la phase Websockets je crois

## Définition et appel des méthodes
@app.get("/exchanges/{exchange}/pairs")
async def get_trading_pairs(exchange: str):
...
 
le @app.get ça sera la forme que va prendre l’appel de la méthode dans la partie client 
et c’est associé sur notre serveur à get_trading_pairs()

côté client : 
def fetch_trading_pairs(exchange: str):
    response = requests.get(f"http://localhost:8000/exchanges/{exchange}/pairs")
    return response.json()

### possibiité d’ajouter pleins de paramètres : 

@app.get("/klines/{exchange}/{symbol}") -> ce que l’utilisateur fait/écrit
async def get_klines(exchange: str, symbol: str, interval: str = Query(..., regex="^[1-9][0-9]*[mhd]$"), limit: Optional[int] = 100): -> la méthode associée derrière
  
On précise les paramètres dans notre demande côté client : 
    response = requests.get(f"http://localhost:8000/klines/{exchange}/{symbol}", params={"interval": interval, "limit": limit})
### possibilité de sécuriser les requêtes avec des authentifications
@app.get("/orders", dependencies=[Depends(get_auth_token)])
async def list_orders(token_id: Optional[str] = None): 
…
