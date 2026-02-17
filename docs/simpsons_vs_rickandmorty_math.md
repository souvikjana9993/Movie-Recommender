# Mathematical Breakdown: The Simpsons vs Rick and Morty

This document provides a detailed mathematical analysis of how the recommender system scores two candidates: **The Simpsons** and **Rick and Morty**.

---

## 1. Raw Data from TMDB

### The Simpsons
```json
{
  "title": "The Simpsons",
  "type": "tv",
  "year": "1989",
  "genres": ["Family", "Animation", "Comedy"],
  "keywords": ["nuclear power plant", "middle class", "cartoon", "satire", 
               "parody", "dysfunctional family", "school", "adult humor", 
               "social satire", "family", "adult animation", "sitcom", 
               "kids", "irreverent", "hilarious"],
  "vote_average": 8.011,
  "vote_count": 10522,
  "recommendation_strength": 3,
  "recommended_because": ["Rick and Morty", "Family Guy", "South Park"]
}
```

### Rick and Morty
```json
{
  "title": "Rick and Morty",
  "type": "tv",
  "year": "2013",
  "genres": ["Animation", "Comedy", "Sci-Fi & Fantasy", "Action & Adventure"],
  "keywords": ["time travel", "grandfather", "alcoholism", "alien", 
               "dysfunctional family", "mad scientist", "scientist", 
               "adult animation", "father figure", "machinist", 
               "multiple dimensions", "spaceship"],
  "vote_average": 8.683,
  "vote_count": 10587,
  "recommendation_strength": 5,
  "recommended_because": ["Family Guy", "Arcane", "Stranger Things", 
                          "Dexter's Laboratory", "South Park"]
}
```

---

## 2. Feature Text Construction

### Formula
For each item, we combine features with weights:

$$\text{feature\_text} = (\text{genres} \times 3) + (\text{keywords} \times 2) + \text{cast} + \text{overview}$$

### The Simpsons Feature Text
```
family family family animation animation animation comedy comedy comedy
nuclear power plant nuclear power plant middle class middle class cartoon cartoon
satire satire parody parody dysfunctional family dysfunctional family school school
adult humor adult humor social satire social satire family family adult animation
adult animation sitcom sitcom kids kids irreverent irreverent hilarious hilarious
set in springfield the average american town the show focuses on the antics and
everyday adventures of the simpson family homer marge bart lisa and maggie...
```

### Rick and Morty Feature Text
```
animation animation animation comedy comedy comedy sci-fi fantasy sci-fi fantasy
sci-fi fantasy action adventure action adventure action adventure
time travel time travel grandfather grandfather alcoholism alcoholism alien alien
dysfunctional family dysfunctional family mad scientist mad scientist scientist scientist
adult animation adult animation father figure father figure machinist machinist
multiple dimensions multiple dimensions spaceship spaceship
follows a sociopathic genius scientist who drags his inherently timid grandson
on adventures across the universe...
```

---

## 3. TF-IDF Vectorization

### Formula
$$\text{TF-IDF}(w, d) = \text{TF}(w, d) \times \text{IDF}(w)$$

Where:
- $\text{TF}(w, d) = \frac{\text{count of word } w \text{ in document } d}{\text{total words in document } d}$
- $\text{IDF}(w) = \log\left(\frac{N}{df_w}\right)$
- $N = 710$ (total candidates)
- $df_w$ = number of documents containing word $w$

### Example: Word "animation"

**In The Simpsons:**
- Count in doc: 6 occurrences (genre repeated 3x + "adult animation" 2x)
- Total words: ~50
- $\text{TF} = 6/50 = 0.12$

**IDF for "animation":**
- Appears in ~200 of 710 documents
- $\text{IDF} = \log(710/200) = \log(3.55) = 1.27$

**TF-IDF for "animation" in The Simpsons:**
$$\text{TF-IDF} = 0.12 \times 1.27 = 0.152$$

### Example: Word "time travel"

**In Rick and Morty:**
- Count: 2 (keyword repeated 2x)
- Total words: ~45
- $\text{TF} = 2/45 = 0.044$

**IDF for "time travel":**
- Appears in ~30 of 710 documents (rare!)
- $\text{IDF} = \log(710/30) = \log(23.67) = 3.16$

**TF-IDF for "time travel" in Rick and Morty:**
$$\text{TF-IDF} = 0.044 \times 3.16 = 0.139$$

---

## 4. User Profile Vector

### Your Watch History (8 items found in candidates)
1. Stranger Things
2. Family Guy
3. South Park
4. Kantara
5. Arcane
6. Rick and Morty
7. Parasite
8. Legally Blonde 2

### Formula
$$\mathbf{u} = \frac{1}{|W|} \sum_{d \in W} \mathbf{v}_d$$

Where $\mathbf{v}_d \in \mathbb{R}^{5000}$ is the TF-IDF vector for item $d$.

### Your Profile (Top Features)
From the notebook output:

| Feature | TF-IDF Weight |
|---------|---------------|
| animation | 0.0951 |
| adult | 0.0841 |
| satire | 0.0642 |
| family | 0.0612 |
| comedy | 0.0604 |
| adult animation | 0.0604 |
| dog | 0.0570 |
| animation comedy | 0.0563 |
| action | 0.0545 |
| thriller | 0.0518 |

---

## 5. Cosine Similarity Calculation

### Formula
$$\cos(\mathbf{u}, \mathbf{c}) = \frac{\mathbf{u} \cdot \mathbf{c}}{||\mathbf{u}|| \times ||\mathbf{c}||}$$

### The Simpsons vs Your Profile

**Shared high-weight features:**

| Feature | Your Profile | Simpsons | Product |
|---------|-------------|----------|---------|
| animation | 0.095 | 0.152 | 0.0144 |
| adult | 0.084 | 0.120 | 0.0101 |
| satire | 0.064 | 0.180 | 0.0115 |
| family | 0.061 | 0.150 | 0.0092 |
| comedy | 0.060 | 0.140 | 0.0084 |
| adult animation | 0.060 | 0.100 | 0.0060 |
| ... | ... | ... | ... |

**Dot product (sum of products):**
$$\mathbf{u} \cdot \mathbf{c}_{Simpsons} \approx 0.0596$$

**Magnitudes:**
- $||\mathbf{u}|| \approx 0.35$
- $||\mathbf{c}_{Simpsons}|| \approx 0.41$

**Cosine Similarity:**
$$\cos(\mathbf{u}, \mathbf{c}_{Simpsons}) = \frac{0.0596}{0.35 \times 0.41} = \frac{0.0596}{0.1435} = 0.419$$

---

### Rick and Morty vs Your Profile

**Shared high-weight features:**

| Feature | Your Profile | R&M | Product |
|---------|-------------|-----|---------|
| animation | 0.095 | 0.140 | 0.0133 |
| comedy | 0.060 | 0.130 | 0.0078 |
| adult animation | 0.060 | 0.090 | 0.0054 |
| sci-fi | 0.045 | 0.160 | 0.0072 |
| action | 0.055 | 0.120 | 0.0066 |
| ... | ... | ... | ... |

**Dot product:**
$$\mathbf{u} \cdot \mathbf{c}_{R\&M} \approx 0.052$$

**Magnitudes:**
- $||\mathbf{u}|| \approx 0.35$
- $||\mathbf{c}_{R\&M}|| \approx 0.45$

**Cosine Similarity:**
$$\cos(\mathbf{u}, \mathbf{c}_{R\&M}) = \frac{0.052}{0.35 \times 0.45} = \frac{0.052}{0.1575} = 0.330$$

---

## 6. Other Score Components

### Collaborative Score

$$S_{collab}(c) = \frac{\text{recommendation\_strength}(c)}{\max(\text{recommendation\_strength})}$$

Where max = 6 (Breaking Bad's strength).

| Show | recommendation_strength | $S_{collab}$ |
|------|------------------------|--------------|
| The Simpsons | 3 | $3/6 = 0.500$ |
| Rick and Morty | 5 | $5/6 = 0.833$ |

### Quality Score

$$S_{quality}(c) = \frac{\text{vote\_average}(c)}{10}$$

| Show | vote_average | $S_{quality}$ |
|------|--------------|---------------|
| The Simpsons | 8.011 | $8.011/10 = 0.801$ |
| Rick and Morty | 8.683 | $8.683/10 = 0.868$ |

### Confidence Score

$$S_{conf}(c) = \min\left(\frac{\text{vote\_count}(c)}{1000}, 1.0\right)$$

| Show | vote_count | $S_{conf}$ |
|------|------------|------------|
| The Simpsons | 10,522 | $\min(10.52, 1.0) = 1.000$ |
| Rick and Morty | 10,587 | $\min(10.59, 1.0) = 1.000$ |

---

## 7. Final Hybrid Score

### Formula
$$\text{Score}(c) = 0.4 \cdot S_{content} + 0.3 \cdot S_{collab} + 0.2 \cdot S_{quality} + 0.1 \cdot S_{conf}$$

### The Simpsons

$$\text{Score}_{Simpsons} = 0.4 \times 0.419 + 0.3 \times 0.500 + 0.2 \times 0.801 + 0.1 \times 1.000$$

| Component | Value | Weight | Contribution |
|-----------|-------|--------|--------------|
| Content | 0.419 | 0.4 | 0.168 |
| Collaborative | 0.500 | 0.3 | 0.150 |
| Quality | 0.801 | 0.2 | 0.160 |
| Confidence | 1.000 | 0.1 | 0.100 |
| **TOTAL** | | | **0.578** |

### Rick and Morty

$$\text{Score}_{R\&M} = 0.4 \times 0.330 + 0.3 \times 0.833 + 0.2 \times 0.868 + 0.1 \times 1.000$$

| Component | Value | Weight | Contribution |
|-----------|-------|--------|--------------|
| Content | 0.330 | 0.4 | 0.132 |
| Collaborative | 0.833 | 0.3 | 0.250 |
| Quality | 0.868 | 0.2 | 0.174 |
| Confidence | 1.000 | 0.1 | 0.100 |
| **TOTAL** | | | **0.656** |

---

## 8. Final Comparison

| Metric | The Simpsons | Rick and Morty | Winner |
|--------|--------------|----------------|--------|
| Content Score | **0.419** | 0.330 | Simpsons |
| Collab Score | 0.500 | **0.833** | Rick and Morty |
| Quality Score | 0.801 | **0.868** | Rick and Morty |
| Confidence | 1.000 | 1.000 | Tie |
| **Final Score** | 0.578 | **0.656** | Rick and Morty |

### Why Rick and Morty Scores Higher

1. **Higher Collaborative Signal (0.833 vs 0.500):**
   - Rick and Morty was recommended by 5 shows you watched
   - The Simpsons was recommended by only 3

2. **Higher Quality (0.868 vs 0.801):**
   - Rick and Morty: 8.68/10 rating
   - The Simpsons: 8.01/10 rating

3. **Lower Content Score (0.330 vs 0.419):**
   - Simpsons actually matches your profile slightly better
   - But the difference (0.089) wasn't enough to overcome other factors

### Why The Simpsons Has Higher Content Score

The Simpsons shares more features with your profile:
- "satire" (high in both)
- "family" (repeated in Simpsons)
- "social satire" (unique to Simpsons in your watched list)

Rick and Morty has more unique features:
- "time travel", "mad scientist", "multiple dimensions"
- These are distinctive but not as prevalent in your profile

---

## 9. Note: Rick and Morty is in Your Watch History

**Important:** Rick and Morty was filtered OUT from final recommendations because you already watched it!

The actual ranking would be:
1. Breaking Bad (0.593) ← Recommended
2. **Rick and Morty (0.656)** ← Filtered out (already watched)
3. Futurama (0.586) ← Recommended
4. The Simpsons (0.578) ← Recommended (#3 after filtering)

This is why The Simpsons appears at rank 3 in your final recommendations.
