# scripts/spike.py — verify what test mode actually permits. Run once, record output.
from dotenv import load_dotenv

load_dotenv()
from encore.razorpay_client import RazorpayClient

c = RazorpayClient()
link = c.create_payment_link(50000, "Encore spike: can we create links?", "spike-001")
print("created:", link["id"], link["status"], link["short_url"])
print("fetched:", c.fetch_payment_link(link["id"])["status"])
