# GNU gettext localization for the adventure game.
# Requires: gettext (e.g. brew install gettext)

DOMAIN = adventure
LOCALE_DIR = locale
SRC = main.py

.PHONY: extract update init-fr compile all

# Extract translatable strings from Python sources into a .pot template
extract:
	xgettext -L Python -o $(LOCALE_DIR)/$(DOMAIN).pot \
		--package-name=$(DOMAIN) \
		--package-version=1.0 \
		$(SRC)
	@echo "Tip: set Content-Type charset to UTF-8 in the .pot header when editing."

# Update existing .po files with new strings from .pot
update: extract
	for po in $(LOCALE_DIR)/*/LC_MESSAGES/$(DOMAIN).po; do \
		msgmerge -U "$$po" $(LOCALE_DIR)/$(DOMAIN).pot; \
	done

# Create a new French .po from the template (run once per language)
init-fr:
	msginit -l fr -i $(LOCALE_DIR)/$(DOMAIN).pot -o $(LOCALE_DIR)/fr/LC_MESSAGES/$(DOMAIN).po --no-translator

# Compile all .po files to .mo (required for gettext to load translations)
compile:
	for po in $(LOCALE_DIR)/*/LC_MESSAGES/$(DOMAIN).po; do \
		msgfmt -o "$${po%.po}.mo" "$$po"; \
	done
	@echo "Compiled .mo files in $(LOCALE_DIR)/*/LC_MESSAGES/"

# Extract, then compile (use after editing .po files)
all: extract compile
