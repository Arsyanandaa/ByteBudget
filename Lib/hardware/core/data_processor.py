import json
import pandas as pd
import re
import matplotlib.pyplot as plt
import seaborn as sns
from wordcloud import WordCloud
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from pathlib import Path

def load_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def clean_text(text):
    # 1. Kecilkan huruf (Lowercasing)
    text = text.lower()
    # 2. Hapus karakter spesial & angka (Normalisasi)
    text = re.sub(r'[^a-z\s]', '', text)
    return text

def clean_price(price_str):
    # Ngubah "Rp 1.500.000" jadi 1500000 (Integer)
    if not price_str: return 0
    clean = re.sub(r'[^\d]', '', price_str)
    return int(clean) if clean else 0

def process_and_visualize(json_file):
    data = load_data(json_file)
    df = pd.DataFrame(data)

    # --- NORMALISASI ---
    df['clean_name'] = df['name'].apply(clean_text)
    df['numeric_price'] = df['price'].apply(clean_price)

    # --- TF-IDF & CONTENT BASED FILTERING ---
    tfidf = TfidfVectorizer(stop_words=['dan', 'yang', 'untuk', 'dengan']) # Stopwords Indo simpel
    tfidf_matrix = tfidf.fit_transform(df['clean_name'])
    
    # Hitung Cosine Similarity antar produk
    cosine_sim = cosine_similarity(tfidf_matrix, tfidf_matrix)

    # --- VISUALISASI 1: Heatmap Similarity (Dosen pasti suka) ---
    plt.figure(figsize=(10, 8))
    sns.heatmap(cosine_sim[:10, :10], annot=True, cmap='YlGnBu', 
                xticklabels=df['name'][:10].str[:15], 
                yticklabels=df['name'][:10].str[:15])
    plt.title("Matrix Kemiripan Produk (Top 10)")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('similarity_heatmap.png')
    plt.show()

    # --- VISUALISASI 2: Word Cloud ---
    all_text = " ".join(df['clean_name'])
    wordcloud = WordCloud(width=800, height=400, background_color='white').generate(all_text)
    plt.figure(figsize=(10, 5))
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis('off')
    plt.title("Kata yang Paling Sering Muncul di Hasil Scraping")
    plt.savefig('wordcloud_products.png')
    plt.show()

    print("✅ Normalisasi Selesai!")
    print(f"📊 Visualisasi disimpan sebagai 'similarity_heatmap.png' dan 'wordcloud_products.png'")

if __name__ == "__main__":
    # Sesuaikan path ke file json lu
    INPUT_FILE = Path("..") / "data_tokped.json"
    process_and_visualize(INPUT_FILE)