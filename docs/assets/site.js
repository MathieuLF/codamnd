(() => {
  const repo = "MathieuLF/codamnd";
  const apiUrl = `https://api.github.com/repos/${repo}/releases?per_page=20`;
  const releasesUrl = `https://github.com/${repo}/releases`;
  const requestTimeoutMs = 5000;
  const card = document.querySelector("[data-release-card]");

  if (!card) {
    return;
  }

  const title = document.querySelector("#release-title");
  const summary = card.querySelector("[data-release-summary]");
  const details = card.querySelector("[data-release-details]");
  const packageTarget = card.querySelector("[data-release-package]");
  const shaTarget = card.querySelector("[data-release-sha]");
  const verificationTarget = card.querySelector("[data-release-verification]");
  const primaryDownloadLink = document.querySelector("[data-primary-download]");
  const virusTotalLink = card.querySelector("[data-release-virustotal]");
  const releasePageLink = card.querySelector("[data-release-page]");
  const note = card.querySelector("[data-release-note]");

  const setText = (element, value) => {
    if (element) {
      element.textContent = value;
    }
  };

  const setHidden = (element, hidden) => {
    if (element) {
      element.hidden = hidden;
    }
  };

  const setUnavailable = (heading, message, noteText) => {
    setText(title, heading);
    setText(summary, message);
    if (details) {
      details.hidden = true;
    }
    if (primaryDownloadLink) {
      primaryDownloadLink.href = releasesUrl;
    }
    if (virusTotalLink) {
      virusTotalLink.hidden = true;
      virusTotalLink.href = releasesUrl;
    }
    if (releasePageLink) {
      releasePageLink.href = releasesUrl;
    }
    if (note) {
      note.hidden = false;
    }
    setText(note, noteText);
  };

  const trustedGithubUrl = (value, fallback = releasesUrl) => {
    try {
      const url = new URL(String(value || ""));
      if (url.protocol === "https:" && (url.hostname === "github.com" || url.hostname.endsWith(".githubusercontent.com"))) {
        return url.href;
      }
    } catch (_error) {
      // Une URL absente ou invalide conserve la destination officielle de repli.
    }
    return fallback;
  };

  const findAsset = (assets, pattern, rejectPattern = null) =>
    assets.find((asset) => {
      const name = asset.name || "";
      return pattern.test(name) && (!rejectPattern || !rejectPattern.test(name));
    });

  // Les versions déjà publiées gardent leur ancien nom jusqu'au prochain exécutable.
  const findPackage = (assets) =>
    findAsset(assets, /^(?:CodaMND|EmployeurD-MegaGest)-v[^/\\]+-portable\.zip$/i);

  const findSha = (assets, packageName) => {
    if (packageName) {
      const escaped = packageName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const directMatch = findAsset(assets, new RegExp(`${escaped}\\.sha256$`, "i"));
      return directMatch || null;
    }
    return findAsset(assets, /\.sha256$/i);
  };

  const findVirusTotal = (assets) => findAsset(assets, /virustotal.*\.md$/i);

  const publicVirusTotalReportUrl = (asset) =>
    asset ? trustedGithubUrl(asset.browser_download_url, releasesUrl) : releasesUrl;

  const shaFromAssetDigest = (asset) => {
    const digest = asset && asset.digest ? String(asset.digest) : "";
    const match = digest.match(/sha256:([a-f0-9]{64})/i);
    return match ? match[1].toUpperCase() : "";
  };

  const shaFromFile = async (asset, signal) => {
    if (!asset || !asset.browser_download_url) {
      return "";
    }
    try {
      const response = await fetch(trustedGithubUrl(asset.browser_download_url), { cache: "no-store", signal });
      if (!response.ok) {
        return "";
      }
      const text = await response.text();
      const match = text.match(/[a-f0-9]{64}/i);
      return match ? match[0].toUpperCase() : "";
    } catch (_error) {
      return "";
    }
  };

  const hydrate = async () => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), requestTimeoutMs);
    try {
      const response = await fetch(apiUrl, {
        headers: { Accept: "application/vnd.github+json" },
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) {
        setUnavailable(
          "Version non vérifiée",
          "GitHub Releases n'a pas répondu correctement.",
          "Consultez directement GitHub pour vérifier les fichiers disponibles."
        );
        return;
      }

      const releases = await response.json();
      const release = Array.isArray(releases)
        ? releases.find((item) => item && typeof item === "object" && !item.draft && !item.prerelease)
        : null;

      if (!release) {
        setUnavailable(
          "Aucune version publiée",
          "Aucune mise en ligne officielle n'est disponible pour le moment.",
          "Consultez GitHub Releases pour connaître l'état des publications."
        );
        return;
      }

      const assets = Array.isArray(release.assets) ? release.assets : [];
      const packageAsset = findPackage(assets);
      const shaAsset = packageAsset ? findSha(assets, packageAsset.name) : null;
      const virusTotalAsset = findVirusTotal(assets);
      const releaseUrl = trustedGithubUrl(release.html_url);
      const published = release.published_at ? new Date(release.published_at) : null;
      const publishedText = published && !Number.isNaN(published.getTime())
        ? published.toLocaleDateString("fr-CA", { year: "numeric", month: "long", day: "numeric" })
        : "date non publiée";

      setText(title, release.name || release.tag_name || "Version publiée");
      setText(summary, `Mise en ligne officielle publiée le ${publishedText}.`);
      if (details) {
        details.hidden = false;
      }
      if (releasePageLink) {
        releasePageLink.href = releaseUrl;
      }

      if (packageAsset) {
        setText(packageTarget, packageAsset.name || "ZIP portable");
        if (primaryDownloadLink) {
          primaryDownloadLink.href = trustedGithubUrl(packageAsset.browser_download_url, releaseUrl);
        }
      } else {
        setText(packageTarget, "Aucun ZIP portable disponible pour cette version.");
        if (primaryDownloadLink) {
          primaryDownloadLink.href = releaseUrl;
        }
      }

      const shaValue = shaFromAssetDigest(packageAsset) || await shaFromFile(shaAsset, controller.signal);
      setText(shaTarget, shaValue || "Non publiée avec cette mise en ligne.");

      if (virusTotalAsset) {
        setText(verificationTarget, "");
        setHidden(verificationTarget, true);
        if (virusTotalLink) {
          virusTotalLink.href = publicVirusTotalReportUrl(virusTotalAsset);
          virusTotalLink.textContent = "Rapport VirusTotal";
          virusTotalLink.hidden = false;
        }
      } else {
        setHidden(verificationTarget, false);
        setText(verificationTarget, "Rapport VirusTotal non joint à cette mise en ligne.");
        if (virusTotalLink) {
          virusTotalLink.hidden = true;
        }
      }

      if (releasePageLink) {
        releasePageLink.textContent = "Toutes les versions";
      }

      if (note) {
        note.hidden = true;
      }
    } catch (_error) {
      setUnavailable(
        "Version non vérifiée",
        "Impossible de joindre GitHub Releases pour le moment.",
        "Réessayez plus tard ou consultez directement GitHub."
      );
    } finally {
      window.clearTimeout(timeout);
      card.setAttribute("aria-busy", "false");
    }
  };

  hydrate();
})();
