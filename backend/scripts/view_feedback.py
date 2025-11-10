# backend/view_feedback.py
import json
from pathlib import Path
from collections import Counter

feedback_dir = Path("logs/feedback")

ratings = []
accuracy_ratings = []
would_pay_yes = 0
would_pay_no = 0
comments = []

for file in sorted(feedback_dir.glob("*.json")):
    data = json.loads(file.read_text())
    ratings.append(data["rating"])
    if data.get("accuracy_rating"):
        accuracy_ratings.append(data["accuracy_rating"])
    if data.get("would_pay") is True:
        would_pay_yes += 1
    elif data.get("would_pay") is False:
        would_pay_no += 1
    if data.get("comment"):
        comments.append({
            "rating": data["rating"],
            "comment": data["comment"]
        })

print(f"📊 Feedback Summary")
print(f"Total feedback: {len(ratings)}")
print(f"Average rating: {sum(ratings)/len(ratings):.1f}/5" if ratings else "No ratings")
print(f"Rating distribution: {dict(Counter(ratings))}")
print(f"\nAccuracy: {sum(accuracy_ratings)/len(accuracy_ratings):.1f}/5" if accuracy_ratings else "No accuracy ratings")
print(f"\nWould pay: {would_pay_yes} yes, {would_pay_no} no")
print(f"\n💬 Comments ({len(comments)}):")
for c in comments:
    print(f"  [{c['rating']}⭐] {c['comment'][:100]}...")