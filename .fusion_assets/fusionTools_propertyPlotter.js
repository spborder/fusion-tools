window.fusionTools = Object.assign({}, window.fusionTools, {
    propertyPlotter: {
        removeMarker: function(e, ctx) {
                e.target.removeLayer(e.layer._leaflet_id);
                ctx.data.features.splice(ctx.data.features.indexOf(e.layer.feature), 1);
            }

            ,
        tooltipMarker: function(feature, layer, ctx) {
            layer.bindTooltip("Double-click to remove")
        },
        markerRender: function(feature, latlng, context) {
            marker = L.marker(latlng, {
                title: "PropertyPlotter Marker",
                alt: "PropertyPlotter Marker",
                riseOnHover: true,
                draggable: false,
            });

            return marker;
        }

    }
});