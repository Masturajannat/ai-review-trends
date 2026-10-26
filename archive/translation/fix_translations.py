from pathlib import Path
import pandas as pd
import re

# Locate the folder containing this Python script
BASE_DIR = Path(__file__).resolve().parent

# Read the original CSV from the same folder
input_file = BASE_DIR / "combined_reviews_translated.csv"
df = pd.read_csv(input_file, dtype=str)

# Fix the five missing English translations
fixes = {
    662: "Excellent product! 100% authentic Hoco EQ34 Plus. Just as it was shown in the description, I got exactly the same. Quality, finishing and packaging everything was very good. Sound quality is very impressive—voice is crystal clear, bass is deep and balanced. ANC feature works very well, surrounding noise gets reduced a lot. Transparency Mode is also very useful. Because of app support, ANC Mode and Transparency Mode can be adjusted from level 1 to 10, and noise control can be customized according to personal needs. Touch controls and other settings can also be easily customized from the app, which makes the overall user experience more premium. Build quality gives a premium feel, fitting is very comfortable, touch controls are smooth, connection is stable and battery backup is also very good. Getting so many features and this performance at this budget, I am really impressed. Seller sent a genuine product. My overall experience was very good. Those who want to buy original Hoco EQ34 Plus Rima can order without any worry. Highly Recommended!",

    2552: 'Rokomari Bookworm Review Competition #Written by- Araf Zayad #Book- Barof Gola Nodi #Author- Zahir Raihan Price: 119৳ Type: Classic Novel Publisher: Anupam. Story Summary: The organized history of the events of the monotonous life of the lower-middle-class society is the main ingredient of the story of this novel. This younger brother of Shahidullah Kaiser has a good reputation as a writer of life’s reality. This novel is a real mirror of that. Mahmud is the central character. At first, he works as a reporter in a newspaper, later, due to not agreeing about salary, he earns his living as a proof checker in another newspaper. He is the pusher of the handcart called family life. In a fragile house with a terrible environment in the unknown alleys of a familiar city, their family consists of father, mother, Mariam, Hasina, Khokon and Dulu. Even while being in family life, Mahmud moves around with an indifferent attitude. As if he is there but not there. To him, father, mother, brothers and sisters are only a few words created by humans. Why is there so much responsibility towards these words????? Due to having very bitter experience about reality, Mahmud has a somewhat loose-tongued nature. He can say many inappropriate things in a pleasant manner, which we get proof of from his opinion about Mansur, Mariam’s fiancé. Basically, he has a nose-turning attitude towards the upper class, and he is suspicious about the ways of rising to the upper class too!!!! Besides Mahmud, there are important side characters like Mariam’s student Selina, friend Lily, Lily’s maternal cousin Taslim, with whom Hasina’s heart dealings started dramatically later on under the excuse of learning the tricks of taking pictures. There are also Mahmud’s friend Shahadat, his friend’s wife Amena, and Naim. In total, around a dozen characters are present. Mariam, who is deprived of her husband’s affection, is the complete victim of the fact that some harsh truths of life have to be hidden. Even for happiness, some unnecessary truths have to be suppressed according to the demand of time. Mariam could not understand this. Basically, the structure of the novel has been built on the basis of the struggles of a middle-class family. At the end of the novel, all the other members of the family except Mahmud die due to the sudden collapse of the house. A complete change comes in Mahmud’s life. The same Mahmud, whose attitude towards life and family was bitter, irritated, sour, uninterested, tasteless and detached, eventually became a family man with his wife and daughter!!!!! Here, Barof Gola Nodi basically means Mahmud’s mind. The mind frozen by the ice of hurt feelings finally started its journey towards the traditional family life.',

    2688: "My best story of all time🥰",
    2690: "A very beautiful book🤗💞",
    2869: "This was helpful!✨",
}

# Check that the requested row indexes exist
missing_rows = [row for row in fixes if row not in df.index]

if missing_rows:
    raise IndexError(
        f"These row indexes were not found in the CSV: {missing_rows}"
    )

# Apply the translation fixes
for row, text in fixes.items():
    df.loc[row, "translated_review_en"] = text

# Remove 'Read More' only when it appears at the end of review_text
read_more_pattern = r"\s*Read More\s*$"

reviews = df["review_text"].fillna("")

read_more_count = reviews.str.contains(
    read_more_pattern,
    case=False,
    regex=True
).sum()

df["review_text"] = reviews.apply(
    lambda text: re.sub(
        read_more_pattern,
        "",
        text,
        flags=re.IGNORECASE
    )
)

# Save a new CSV beside this script; preserve the original file
output_file = BASE_DIR / "combined_reviews_translated_fixed.csv"

df.to_csv(
    output_file,
    index=False,
    encoding="utf-8-sig"
)

# Verify the results
remaining_read_more = df["review_text"].fillna("").str.contains(
    read_more_pattern,
    case=False,
    regex=True
).sum()

print("\nFinished!")
print(f"Input file: {input_file.name}")
print(f"Output file: {output_file.name}")
print(f"Translations filled: {len(fixes)}")
print(f"Trailing 'Read More' labels removed: {read_more_count}")
print(f"Trailing 'Read More' labels remaining: {remaining_read_more}")

print("\nCheck the five corrected translations:")
print(
    df.loc[
        list(fixes),
        ["review_text", "translated_review_en"]
    ].to_string()
)

print(f"\nYour cleaned CSV is saved here:\n{output_file}")