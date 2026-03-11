# Gomidas Institute Publications Scraper

This repository contains a scraper that extracts bibliographic metadata from the Gomidas Institute website.

Website: https://www.gomidas.org

The project was prepared for the Open Data Armenia initiative and focuses on creating a structured open dataset of publications listed on the Gomidas Institute website.

## Dataset

The scraper extracts the following fields from each publication page:

| Field | Description |
|------|-------------|
| title | Title of the publication |
| date_or_period | Publication year |
| author_or_creator | Author, editor, or translator |
| description_or_abstract | Description text from the page |
| url_to_original_object | URL of the original publication page |

The dataset is saved as:

data/gomidas_books.csv  
data/gomidas_books.jsonl

All files are UTF‑8 encoded.

## Installation

Clone the repository:

git clone https://github.com/YOUR_USERNAME/gomidas-books-scraper.git
cd gomidas-books-scraper

Install dependencies:

pip install -r requirements.txt

## Usage

Run the scraper:

python main.py

The script will:

1. Crawl the Books catalog
2. Visit each publication page
3. Extract metadata
4. Clean the data
5. Save CSV and JSONL datasets

## Data Source

Gomidas Institute (London)

https://www.gomidas.org/books

