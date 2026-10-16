import os
from sqlalchemy import select
from pwdlib import PasswordHash
from .models import Session, Location, User
password=os.environ.get("SEED_PASSWORD")
if not password or len(password)<12: raise SystemExit("Set SEED_PASSWORD to a unique password of at least 12 characters.")
with Session() as s:
    for letter in "abc":
        slug="parking-"+letter
        loc=s.scalar(select(Location).where(Location.slug==slug))
        if not loc:
            loc=Location(slug=slug,name="Parking "+letter.upper(),rate=3000); s.add(loc); s.flush()
        username="staff-"+letter
        if not s.scalar(select(User).where(User.username==username)):
            s.add(User(username=username,password_hash=PasswordHash.recommended().hash(password),role="staff",location_id=loc.id))
    if not s.scalar(select(User).where(User.username=="owner")):
        s.add(User(username="owner",password_hash=PasswordHash.recommended().hash(password),role="owner"))
    s.commit()
print("Seeded locations and missing accounts: owner, staff-a, staff-b, staff-c. Existing passwords unchanged.")
