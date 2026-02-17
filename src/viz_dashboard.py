
import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import pandas as pd
import numpy as np
import pickle
import os
from sklearn.manifold import TSNE
from sklearn.cluster import KMeans

# Configuration
EMBEDDING_PATH = "data/embeddings.pkl"
METADATA_PATH = "data/candidates.json" # Assuming we have metadata here or in score file
SCORES_PATH = "data/all_scores.json"

def load_data():
    if not os.path.exists(SCORES_PATH) or not os.path.exists(METADATA_PATH):
        print("Data files not found. Run generation script first.")
        return pd.DataFrame()
    
    import json
    # Load Scores
    with open(SCORES_PATH, 'r') as f:
        scores_map = json.load(f)
        
    # Load Metadata (Candidates)
    with open(METADATA_PATH, 'r') as f:
        meta = json.load(f)
        candidates = meta.get("candidates", [])
        
    # Merge
    merged = []
    for item in candidates:
        tmdb_id = str(item.get('tmdb_id'))
        if tmdb_id in scores_map:
            # Combine dicts
            row = item.copy()
            row['score'] = scores_map[tmdb_id].get('hybrid', 0)
            merged.append(row)
            
    df = pd.DataFrame(merged)
    return df

def load_embeddings(df):
    if not os.path.exists(EMBEDDING_PATH):
        return None
    with open(EMBEDDING_PATH, 'rb') as f:
        emb_dict = pickle.load(f)
    
    # Align embeddings with DataFrame
    embeddings = []
    valid_indices = []
    for idx, row in df.iterrows():
        mid = str(row.get('id', row.get('tmdb_id')))
        if mid in emb_dict:
            embeddings.append(emb_dict[mid])
            valid_indices.append(idx)
    
    return np.array(embeddings), df.loc[valid_indices]

# Initialize App
app = dash.Dash(__name__, title="Movie Galaxy 3D")

# Load initial data
df = load_data()
if not df.empty:
    embeddings, df = load_embeddings(df)
    
    print(f"Reducing {len(embeddings)} vectors to 3D...")
    tsne = TSNE(n_components=3, random_state=42, perplexity=min(30, len(embeddings)-1))
    projections = tsne.fit_transform(embeddings)
    
    df['x'] = projections[:, 0]
    df['y'] = projections[:, 1]
    df['z'] = projections[:, 2]

    # Cluster
    kmeans = KMeans(n_clusters=8, random_state=42)
    df['cluster'] = kmeans.fit_predict(embeddings)
    df['cluster'] = df['cluster'].astype(str)

app.layout = html.Div([
    html.H1("Movie Recommendation Galaxy (EmbeddingGemma-300M)", style={'textAlign': 'center', 'color': '#fff'}),
    
    html.Div([
        dcc.Input(id="search-box", type="text", placeholder="Search movie...", style={'padding': '10px', 'width': '300px'}),
    ], style={'textAlign': 'center', 'marginBottom': '20px'}),
    
    dcc.Graph(id="galaxy-plot", style={'height': '80vh'})
], style={'backgroundColor': '#111', 'color': '#ddd', 'minHeight': '100vh', 'fontFamily': 'sans-serif'})

@app.callback(
    Output("galaxy-plot", "figure"),
    [Input("search-box", "value")]
)
def update_graph(search_term):
    if df.empty:
        return px.scatter_3d(title="No Data Available")
    
    filtered_df = df.copy()
    
    # Highlight logic
    if search_term:
        filtered_df['size'] = filtered_df['title'].str.contains(search_term, case=False).map({True: 15, False: 5})
        filtered_df['color_seq'] = filtered_df['title'].str.contains(search_term, case=False).map({True: 'red', False: 'blue'})
    else:
        filtered_df['size'] = 5
        filtered_df['color_seq'] = filtered_df['cluster']

    fig = px.scatter_3d(
        filtered_df, x='x', y='y', z='z',
        color='cluster',
        hover_name='title',
        hover_data=['genres', 'score'],
        size='size',
        opacity=0.8,
        template="plotly_dark",
        title="Semantic Movie Clusters"
    )
    
    fig.update_layout(margin=dict(l=0, r=0, b=0, t=40))
    return fig

if __name__ == '__main__':
    app.run(debug=True, port=8050)
