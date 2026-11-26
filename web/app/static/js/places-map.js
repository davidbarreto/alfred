/*
 * The Places map: one zoomable Leaflet map, world -> country -> city -> places (docs/portal.md, Places map).
 *
 * Markup: <div class="places-map" data-map-data="/places/map/data?city_id=4" data-fit="city"></div>
 *   data-fit: "world" (default), "country" or "city": what the first view is fitted to.
 * Needs Leaflet and Leaflet.markercluster loaded first (_places_map_assets.html).
 *
 * Layers: the vendored country shapes (world.json, keyed by ISO alpha-2), tinted for the countries Alfred knows and
 * faded as you zoom in; city markers (the home city marked); place pins, clustered, coloured by kind group. The
 * basemap is OpenStreetMap's tiles greyed by CSS (inverted in dark mode); the shapes and markers draw without it.
 * Touch: one finger scrolls the page, two fingers pinch and move the map.
 * Page hooks: [data-map-toggle="cities"|"places"] checkboxes; [data-map-place="<id>"] rows pulse and pan to a pin.
 */
(function () {
  'use strict';

  var WORLD_URL = '/static/js/world.json';
  var TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  var ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors';
  // Street zoom: from here names show next to the pins.
  var LABEL_ZOOM = 15;
  // The known countries' tint fades out between these zooms, so it never hides streets.
  var TINT_FULL_ZOOM = 3;
  var TINT_NONE_ZOOM = 7;
  var worldPromise = null;

  function esc(text) {
    return String(text == null ? '' : text).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function loadWorld() {
    if (!worldPromise) {
      worldPromise = fetch(WORLD_URL).then(function (r) {
        if (!r.ok) throw new Error('world ' + r.status);
        return r.json();
      }).catch(function () { worldPromise = null; return { type: 'FeatureCollection', features: [] }; });
    }
    return worldPromise;
  }

  function coarsePointer() {
    return window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
  }

  function placeIcon(place) {
    var home = place.kind === 'home';
    return L.divIcon({
      className: 'pm-pin-wrap',
      html: '<span class="pm-pin pm-group-' + esc(place.group) + (home ? ' pm-pin-home' : '') + '" data-pin="' + place.id + '"><i class="ti ' + esc(place.icon) + '"></i></span>',
      iconSize: home ? [34, 34] : [28, 28],
      iconAnchor: home ? [17, 17] : [14, 14],
      popupAnchor: [0, -14],
      tooltipAnchor: [16, 0],
    });
  }

  function cityIcon(city) {
    return L.divIcon({
      className: 'pm-city-wrap',
      html: '<span class="pm-city' + (city.home ? ' pm-city-home' : '') + '"><i class="ti ' + (city.home ? 'ti-home' : 'ti-building-community') + '"></i><span class="pm-city-name">' + esc(city.name) + '</span></span>',
      iconSize: null,
      iconAnchor: [14, 14],
    });
  }

  function placePopup(place) {
    return '<div class="pm-popup"><a class="pm-popup-title" href="/places/' + place.id + '">' + esc(place.name) + '</a>' +
      '<p>' + esc(place.kind.replace(/_/g, ' ')) + ' · ' + esc(place.city_name) + '</p>' +
      '<p><a href="/places/' + place.id + '">Open</a> · <a href="' + esc(place.maps_link) + '" target="_blank" rel="noopener noreferrer">Maps</a></p></div>';
  }

  function tintOpacity(zoom) {
    if (zoom <= TINT_FULL_ZOOM) return 1;
    if (zoom >= TINT_NONE_ZOOM) return 0;
    return 1 - (zoom - TINT_FULL_ZOOM) / (TINT_NONE_ZOOM - TINT_FULL_ZOOM);
  }

  function PlacesMap(el) {
    this.el = el;
    this.fit = el.dataset.fit || 'world';
    this.pins = {};
    var touch = coarsePointer();
    this.map = L.map(el, {
      worldCopyJump: true,
      minZoom: 1,
      maxZoom: 19,
      zoomSnap: 0.5,
      // On a phone one finger scrolls the page; Leaflet's pinch handler zooms and moves with two.
      dragging: !touch,
      scrollWheelZoom: !touch,
    }).setView([25, 10], 2);
    L.tileLayer(TILES, { attribution: ATTRIBUTION, maxZoom: 19, className: 'pm-tiles' }).addTo(this.map);
    if (touch) el.insertAdjacentHTML('beforeend', '<div class="pm-hint">Two fingers to move the map</div>');
    this.bar = document.createElement('div');
    this.bar.className = 'pm-bar';
    this.bar.hidden = true;
    el.appendChild(this.bar);
    L.DomEvent.disableClickPropagation(this.bar);
    this.map.on('zoomend', this.onZoom.bind(this));
  }

  PlacesMap.prototype.load = function () {
    var self = this;
    return Promise.all([
      fetch(self.el.dataset.mapData, { headers: { Accept: 'application/json' } }).then(function (r) {
        if (!r.ok) throw new Error('map ' + r.status);
        return r.json();
      }),
      loadWorld(),
    ]).then(function (results) {
      self.draw(results[0], results[1]);
    }).catch(function () {
      self.el.insertAdjacentHTML('beforeend', '<div class="pm-error">The map could not be loaded.</div>');
    });
  };

  PlacesMap.prototype.draw = function (data, world) {
    var self = this;
    var known = {};
    data.countries.forEach(function (c) { if (c.code) known[c.code] = c; });
    this.data = data;

    this.countries = L.geoJSON(world, {
      style: function (f) { return self.countryStyle(known[f.properties.code]); },
      onEachFeature: function (f, layer) {
        var country = known[f.properties.code];
        layer.on('click', function (e) {
          L.DomEvent.stopPropagation(e);
          self.map.fitBounds(layer.getBounds(), { padding: [20, 20], maxZoom: 7 });
          self.showBar(country, f.properties.name);
        });
        if (country) layer.bindTooltip(esc(country.name), { sticky: true, className: 'pm-tooltip' });
      },
    }).addTo(this.map);
    this.known = known;

    this.cities = L.layerGroup();
    data.cities.forEach(function (city) {
      L.marker([city.latitude, city.longitude], { icon: cityIcon(city), zIndexOffset: 500, title: city.name })
        .on('click', function () { window.location.href = '/places/cities/' + city.id; })
        .addTo(self.cities);
    });
    this.cities.addTo(this.map);

    this.places = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 40, spiderfyOnMaxZoom: true });
    data.places.forEach(function (place) {
      var marker = L.marker([place.latitude, place.longitude], { icon: placeIcon(place), title: place.name })
        .bindPopup(placePopup(place))
        .bindTooltip(esc(place.name), { permanent: true, direction: 'right', className: 'pm-label' });
      self.pins[place.id] = marker;
      self.places.addLayer(marker);
    });
    this.places.addTo(this.map);

    this.fitView(world);
    this.onZoom();
    this.bindPage();
  };

  PlacesMap.prototype.countryStyle = function (country) {
    var opacity = tintOpacity(this.map.getZoom());
    if (country) {
      return { className: 'pm-country pm-country-known', weight: 1, fillOpacity: 0.55 * opacity, opacity: 0.9 * Math.max(opacity, 0.3) };
    }
    return { className: 'pm-country', weight: 0.5, fillOpacity: 0.15 * opacity, opacity: 0.4 * opacity };
  };

  PlacesMap.prototype.fitView = function (world) {
    var points = this.data.places.map(function (p) { return [p.latitude, p.longitude]; })
      .concat(this.data.cities.map(function (c) { return [c.latitude, c.longitude]; }));
    if (this.fit === 'city' && points.length) {
      this.map.fitBounds(L.latLngBounds(points), { padding: [30, 30], maxZoom: 14 });
      return;
    }
    if (this.fit === 'country') {
      var code = this.data.countries.length === 1 ? this.data.countries[0].code : null;
      var shape = code && world.features.filter(function (f) { return f.properties.code === code; })[0];
      if (shape) {
        this.map.fitBounds(L.geoJSON(shape).getBounds(), { padding: [10, 10], maxZoom: 8 });
        return;
      }
      if (points.length) {
        this.map.fitBounds(L.latLngBounds(points), { padding: [30, 30], maxZoom: 10 });
        return;
      }
    }
    // The world: the countries Alfred knows, or the whole map when there are none.
    var self = this;
    var bounds = null;
    this.countries.eachLayer(function (layer) {
      if (self.known[layer.feature.properties.code]) {
        // A copy: a layer's getBounds() is its own object, which extend() would change.
        var own = layer.getBounds();
        bounds = (bounds || L.latLngBounds(own.getSouthWest(), own.getNorthEast())).extend(own);
      }
    });
    if (this.fit === 'world' && bounds) this.map.fitBounds(bounds, { padding: [20, 20], maxZoom: 4 });
  };

  PlacesMap.prototype.onZoom = function () {
    var zoom = this.map.getZoom();
    this.el.classList.toggle('pm-labels', zoom >= LABEL_ZOOM);
    this.el.classList.toggle('pm-city-names', zoom >= 4);
    var self = this;
    if (this.countries) this.countries.setStyle(function (f) { return self.countryStyle(self.known[f.properties.code]); });
  };

  PlacesMap.prototype.showBar = function (country, shapeName) {
    if (!country) {
      this.bar.innerHTML = '<span>' + esc(shapeName) + '</span><span class="pm-bar-muted">not in Alfred</span>';
    } else {
      var cities = country.city_count === 1 ? '1 city' : country.city_count + ' cities';
      this.bar.innerHTML = '<strong>' + esc(country.name) + '</strong><span class="pm-bar-muted">' + cities + '</span>' +
        '<a href="/places/countries/' + country.id + '">Open</a>';
    }
    this.bar.insertAdjacentHTML('beforeend', '<button type="button" aria-label="Close">&times;</button>');
    var bar = this.bar;
    bar.querySelector('button').addEventListener('click', function () { bar.hidden = true; });
    bar.hidden = false;
  };

  PlacesMap.prototype.toggle = function (layer, on) {
    var group = layer === 'cities' ? this.cities : this.places;
    if (!group) return;
    if (on) group.addTo(this.map); else this.map.removeLayer(group);
  };

  PlacesMap.prototype.focus = function (placeId) {
    var marker = this.pins[placeId];
    if (!marker) return;
    var self = this;
    this.places.zoomToShowLayer(marker, function () {
      self.map.panTo(marker.getLatLng());
      var pin = marker.getElement() && marker.getElement().querySelector('.pm-pin');
      if (!pin) return;
      pin.classList.remove('pm-pulse');
      void pin.offsetWidth;  // restart the animation
      pin.classList.add('pm-pulse');
    });
  };

  PlacesMap.prototype.bindPage = function () {
    var self = this;
    document.querySelectorAll('[data-map-toggle]').forEach(function (box) {
      box.addEventListener('change', function () { self.toggle(box.dataset.mapToggle, box.checked); });
      self.toggle(box.dataset.mapToggle, box.checked);
    });
    document.querySelectorAll('[data-map-place]').forEach(function (row) {
      var id = row.dataset.mapPlace;
      if (!self.pins[id]) return;
      row.addEventListener('mouseenter', function () { self.focus(id); });
      row.addEventListener('focus', function () { self.focus(id); });
    });
  };

  function init() {
    if (typeof L === 'undefined' || !L.markerClusterGroup) return;
    document.querySelectorAll('.places-map[data-map-data]').forEach(function (el) {
      if (el._placesMap) return;
      el._placesMap = new PlacesMap(el);
      el._placesMap.load();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
