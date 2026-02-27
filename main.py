"""
╔══════════════════════════════════════════════════════════════╗
║        LOAD TESTING BLACK BOX — MONTÉE EN CHARGE             ║
║                  Python + Locust                              ║
╠══════════════════════════════════════════════════════════════╣
║  Mode : Black Box — aucune connaissance du site requise       ║
║  Le script crawle automatiquement les liens de la homepage    ║
║  puis les utilise comme cibles de test.                       ║
╠══════════════════════════════════════════════════════════════╣
║  INSTALLATION :                                               ║
║    pip install locust requests beautifulsoup4                 ║
║                                                               ║
║  LANCEMENT (interface web) :                                  ║
║    locust -f loadtest.py --host=https://votresite.com         ║
║    Puis ouvrir : http://localhost:8089                        ║
║                                                               ║
║  LANCEMENT AUTOMATIQUE (headless + rapport CSV) :             ║
║    locust -f loadtest.py --host=https://votresite.com \       ║
║           --headless --csv=rapport                            ║
╚══════════════════════════════════════════════════════════════╝
"""

import random
import logging
import requests
from urllib.parse import urlparse, urljoin, urldefrag
from bs4 import BeautifulSoup

from locust import HttpUser, task, between, events
from locust.shape import LoadTestShape


# ─────────────────────────────────────────────
# ⚙️  CONFIGURATION
# ─────────────────────────────────────────────

PALIERS = [
    # (nb_users, spawn_rate, duree_secondes, label)
    (1,    1,   30, "Palier 1  ->   1 utilisateur"),
    (20,   5,   30, "Palier 2  ->  20 utilisateurs"),
    (50,   10,  30, "Palier 3  ->  50 utilisateurs"),
    (100,  20,  30, "Palier 4  -> 100 utilisateurs"),
    (500,  50,  30, "Palier 5  -> 500 utilisateurs"),
]

# Temps d'attente entre requetes d'un utilisateur simule (secondes)
WAIT_MIN = 1
WAIT_MAX = 3

# Profondeur max du crawl (1 = homepage uniquement, 2 = homepage + ses liens)
CRAWL_DEPTH = 2

# Nombre max d'URLs a decouvrir (evite les sites tres larges)
MAX_URLS = 30

# Timeout pour le crawl (secondes)
CRAWL_TIMEOUT = 10

# Stockage partage des URLs decouvertes entre tous les workers
discovered_urls: list = []

# Garde : le crawl ne doit s'executer qu'une seule fois
# (Locust 2.x declenche test_start une fois par palier avec LoadTestShape)
_crawl_done = False


# ─────────────────────────────────────────────
# 🕷️  CRAWLER BLACK BOX
# ─────────────────────────────────────────────

class BlackBoxCrawler:
    """
    Crawle automatiquement un site pour decouvrir ses URLs internes.
    Ne requiert aucune connaissance prealable de la structure du site.
    """

    def __init__(self, base_url, max_depth=2, max_urls=30):
        self.base_url = base_url.rstrip("/")
        self.domain = urlparse(base_url).netloc
        self.max_depth = max_depth
        self.max_urls = max_urls
        self.visited = set()
        self.found_urls = []

    def crawl(self):
        """Lance le crawl et retourne la liste des URLs decouvertes."""
        print("\n" + "-"*55, flush=True)
        print(f"  [CRAWL] Analyse de : {self.base_url}", flush=True)
        print(f"  Profondeur : {self.max_depth} | Max URLs : {self.max_urls}", flush=True)
        print("-"*55, flush=True)

        self._crawl_url(self.base_url, depth=0)

        # Toujours inclure la racine
        if "/" not in self.found_urls:
            self.found_urls.insert(0, "/")

        print(f"\n  {len(self.found_urls)} URL(s) decouvertes :\n", flush=True)
        for url in self.found_urls:
            print(f"    - {url}", flush=True)
        print("-"*55 + "\n", flush=True)

        return self.found_urls

    def _crawl_url(self, url, depth):
        """Crawle recursivement une URL jusqu'a la profondeur max."""
        if depth > self.max_depth:
            return
        if len(self.found_urls) >= self.max_urls:
            return
        if url in self.visited:
            return

        self.visited.add(url)

        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; LoadTester/1.0; "
                    "+https://github.com/locustio/locust)"
                )
            }
            response = requests.get(
                url,
                timeout=CRAWL_TIMEOUT,
                headers=headers,
                allow_redirects=True
            )

            # N'indexe que les pages HTML
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                return

            # Extraire le chemin relatif
            path = urlparse(response.url).path or "/"
            if path not in self.found_urls:
                self.found_urls.append(path)

            # Parser les liens de la page
            soup = BeautifulSoup(response.text, "html.parser")
            links = self._extraire_liens_internes(soup, response.url)

            # Crawler recursivement
            for link in links:
                if len(self.found_urls) >= self.max_urls:
                    break
                self._crawl_url(link, depth + 1)

        except requests.exceptions.SSLError:
            logging.warning(f"  SSL error sur {url} — passage en HTTP")
            if url.startswith("https://"):
                self._crawl_url(url.replace("https://", "http://", 1), depth)
        except requests.exceptions.ConnectionError:
            logging.warning(f"  Connexion impossible : {url}")
        except requests.exceptions.Timeout:
            logging.warning(f"  Timeout sur : {url}")
        except Exception as e:
            logging.warning(f"  Erreur sur {url} : {e}")

    def _extraire_liens_internes(self, soup, page_url):
        """Extrait tous les liens internes d'une page HTML."""
        liens = []
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()

            # Ignorer les liens vides, ancres, mailto, tel, javascript
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            # Construire l'URL absolue
            full_url, _ = urldefrag(urljoin(page_url, href))
            parsed = urlparse(full_url)

            # Garder uniquement les liens du meme domaine
            if parsed.netloc != self.domain:
                continue

            # Ignorer les fichiers non-HTML classiques
            ignored_ext = (
                ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
                ".pdf", ".zip", ".mp4", ".mp3", ".css", ".js",
                ".ico", ".woff", ".woff2", ".ttf", ".xml", ".json"
            )
            if any(parsed.path.lower().endswith(ext) for ext in ignored_ext):
                continue

            if full_url not in self.visited:
                liens.append(full_url)

        return liens


# ─────────────────────────────────────────────
# 📐 FORME DE CHARGE EN PALIERS
# ─────────────────────────────────────────────

class StepLoadShape(LoadTestShape):
    """Montee en charge automatique par paliers."""

    def __init__(self):
        super().__init__()
        self._palier_actuel = -1

    def tick(self):
        elapsed = self.get_run_time()
        temps_cumule = 0

        for index, (nb_users, spawn_rate, duree, label) in enumerate(PALIERS):
            temps_cumule += duree
            if elapsed < temps_cumule:
                if index != self._palier_actuel:
                    self._palier_actuel = index
                    logging.info("\n" + "="*52)
                    logging.info(f"  >> {label}")
                    logging.info(f"  Duree : {duree}s | Spawn rate : {spawn_rate}/s")
                    logging.info("="*52)
                return (nb_users, spawn_rate)

        return None  # Fin du test


# ─────────────────────────────────────────────
# 👤 COMPORTEMENT DE L'UTILISATEUR SIMULE
# ─────────────────────────────────────────────

class WebsiteUser(HttpUser):
    """
    Utilisateur simule en mode black box.
    Navigue aleatoirement sur les URLs decouvertes par le crawler.
    """

    wait_time = between(WAIT_MIN, WAIT_MAX)

    @task
    def visiter_page_decouverte(self):
        """
        Visite une URL aleatoire parmi celles decouvertes.
        Si aucune URL n'a ete trouvee, teste uniquement '/'.
        """
        urls = discovered_urls if discovered_urls else ["/"]
        path = random.choice(urls)

        with self.client.get(
            path,
            name=f"[GET] {path}",
            catch_response=True,
            allow_redirects=True
        ) as response:
            self._valider_reponse(response)

    def _valider_reponse(self, response):
        """Valide la reponse HTTP de facon generique (black box)."""
        if response.status_code in [200, 201]:
            response.success()
        elif response.status_code in [301, 302, 303, 307, 308]:
            response.success()  # Redirections OK
        elif response.status_code == 404:
            response.failure(f"404 Not Found — {response.url}")
        elif response.status_code == 429:
            response.failure("Rate limit atteint (429) — serveur vous ralentit")
        elif response.status_code == 503:
            response.failure("Service indisponible (503)")
        elif response.status_code >= 500:
            response.failure(f"Erreur serveur ({response.status_code})")
        else:
            response.success()  # Autres codes acceptes par defaut


# ─────────────────────────────────────────────
# 📊 EVENEMENTS — Crawl au demarrage + Resume
# ─────────────────────────────────────────────

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Lance le crawl automatique avant le debut du test de charge."""
    global discovered_urls, _crawl_done

    # Locust 2.x avec LoadTestShape declenche test_start a chaque changement
    # de palier. On ne crawle qu'une seule fois.
    if _crawl_done:
        return
    _crawl_done = True

    host = environment.host
    if not host:
        print("  ERREUR : aucun host fourni. Utilisez --host=https://votresite.com", flush=True)
        return

    duree_totale = sum(p[2] for p in PALIERS)

    print("\n" + "="*56, flush=True)
    print("     LOAD TEST BLACK BOX — DEMARRAGE", flush=True)
    print("="*56, flush=True)
    print(f"  Cible         : {host}", flush=True)
    print(f"  Duree estimee : {duree_totale}s", flush=True)
    print(f"  Paliers       : {len(PALIERS)} niveaux", flush=True)
    print("="*56, flush=True)

    # Lancement du crawl
    crawler = BlackBoxCrawler(
        base_url=host,
        max_depth=CRAWL_DEPTH,
        max_urls=MAX_URLS
    )
    discovered_urls = crawler.crawl()

    if not discovered_urls:
        print("  AVERTISSEMENT : Aucune URL decouverte. Seule '/' sera testee.\n", flush=True)
        discovered_urls = ["/"]

    print(f"  {len(discovered_urls)} URL(s) utilisees pour le test de charge.\n", flush=True)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Affiche le resume final du test."""
    stats = environment.stats.total

    p95 = stats.get_response_time_percentile(0.95) or 0
    taux_erreur = (
        (stats.num_failures / stats.num_requests * 100)
        if stats.num_requests > 0 else 0
    )

    print("\n" + "="*56, flush=True)
    print("     TEST TERMINE — RESUME FINAL", flush=True)
    print("="*56, flush=True)
    print(f"  Requetes totales : {stats.num_requests}", flush=True)
    print(f"  Echecs           : {stats.num_failures}", flush=True)
    print(f"  Taux d'erreur    : {taux_erreur:.2f}%", flush=True)
    print(f"  RPS moyen        : {stats.current_rps:.1f}", flush=True)
    print(f"  Latence mediane  : {stats.median_response_time:.1f} ms", flush=True)
    print(f"  Latence P95      : {p95:.1f} ms", flush=True)
    print(f"  Latence max      : {stats.max_response_time:.1f} ms", flush=True)
    print("="*56 + "\n", flush=True)