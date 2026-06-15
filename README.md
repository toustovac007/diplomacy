# Diplomacy-like online multiplayer game

## 📌 O projektu
Tento projekt je webová aplikace inspirovaná hrou Diplomacy (asynchronní korespondenční strategická hra).

Hráči se registrují, přihlašují a mohou se účastnit více her současně. Hra probíhá po kolech, kde každý hráč zadává své tahy. Po uplynutí časového limitu se kolo vyhodnotí a hráči jsou informováni e-mailem.

---

## 🎯 Cíle projektu
- Online multiplayer hra pouze pro reálné hráče
- Systém kol (turn-based gameplay)
- Možnost účasti v několika hrách najednou
- Notifikace hráčů pomocí e-mailu
- Přístup odkudkoliv přes webový prohlížeč
- Jednoduché a přehledné UI

---

## 🏗️ Použité technologie

### Backend
- Django (Python web framework)
- Django REST Framework (API vrstva)
- PostgreSQL (databáze)

### Frontend
Varianta A (doporučeno pro jednoduchost):
- Django Templates (HTML + CSS)
- HTMX pro dynamické části bez nutnosti velkého JavaScriptu

Varianta B (pokročilejší):
- REST API + JavaScript frontend

### Další technologie
- Celery (asynchronní úlohy – vyhodnocení kol, emaily)
- Redis (queue pro Celery)
- SMTP / email service (notifikace hráčů)
- Gunicorn + Nginx (produkční server)

---

## 🧩 Hlavní moduly aplikace

### 👤 Users
- registrace a přihlášení
- správa profilu
- autentizace

### 🎮 Games
- vytvoření hry
- připojení hráčů
- nastavení délky kol
- správa stavu hry

### 🎯 Moves
- ukládání tahů hráčů
- validace tahů
- vyhodnocení kol

### 📬 Notifications
- e-mailová upozornění
- upozornění na začátek/konec kola
- systém fronty zpráv

---

## 🔄 Herní cyklus
1. Vytvoření hry
2. Připojení hráčů
3. Start kola
4. Hráči odešlou tahy
5. Po uplynutí času:
   - vyhodnocení kol
   - aktualizace stavu hry
   - odeslání notifikací
6. Opakování

---

## 📦 Struktura projektu
- backend/
  - config/ (Django settings)
  - apps/
    - users/
    - games/
    - moves/
    - notifications/
  - templates/
  - static/

---

## 🚀 Plán vývoje

### Fáze 1 – základ
- [ ] Setup Django projektu
- [ ] User registrace a login
- [ ] Základní modely (User, Game, Move)
- [ ] Admin panel

### Fáze 2 – herní logika
- [ ] Vytváření a připojení ke hrám
- [ ] Systém kol
- [ ] Ukládání tahů
- [ ] Základní UI

### Fáze 3 – notifikace
- [ ] Email systém
- [ ] Asynchronní zpracování (Celery + Redis)
- [ ] Automatické vyhodnocení kol

### Fáze 4 – UI/UX
- [ ] Vylepšení frontend rozhraní
- [ ] Přehled her a stavů
- [ ] Historie tahů

### Fáze 5 – deployment
- [ ] Nasazení na server
- [ ] Konfigurace domény
- [ ] HTTPS + bezpečnost

---

## 🧠 Poznámky
- Projekt je navržen modulárně, aby bylo možné snadno rozšiřovat herní logiku
- Prioritou je funkční backend, UI je sekundární
- Důraz na asynchronní zpracování kol
