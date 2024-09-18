window.fusionTools = Object.assign({}, window.fusionTools, {
    default: {
        centerMap: function(e, ctx) {
            ctx.map.flyTo([-120, 120], 1);
        },
        featureStyle: function(feature, context) {
                const {
                    overlayBounds,
                    overlayProp,
                    fillOpacity,
                    lineColor,
                    filterVals
                } = context.hideout;
                var style = {};
                if ("min" in overlayBounds) {
                    var csc = chroma.scale(["blue", "red"]).domain([overlayBounds.min, overlayBounds.max]);
                } else if ("unique" in overlayBounds) {
                    var class_indices = overlayBounds.unique.map(str => overlayBounds.unique.indexOf(str));
                    var csc = chroma.scale(["blue", "red"]).colors(class_indices.length);
                } else {
                    style.fillColor = 'white';
                    style.fillOpacity = fillOpacity;
                    if ('name' in feature.properties) {
                        style.color = lineColor[feature.properties.name];
                    } else {
                        style.color = 'white';
                    }

                    return style;
                }

                var overlayVal = Number.Nan;
                if (overlayProp) {
                    if (overlayProp.name) {
                        var overlaySubProps = overlayProp.name.split(" --> ");
                        var prop_dict = feature.properties;
                        for (let i = 0; i < overlaySubProps.length; i++) {
                            if (overlaySubProps[i] in prop_dict) {
                                var prop_dict = prop_dict[overlaySubProps[i]];
                                var overlayVal = prop_dict;
                            } else {
                                var overlayVal = Number.Nan;
                            }
                        }
                    } else {
                        var overlayVal = Number.Nan;
                    }
                } else {
                    var overlayVal = Number.Nan;
                }

                if (overlayVal == overlayVal && overlayVal != null) {
                    if (typeof overlayVal === 'number') {
                        style.fillColor = csc(overlayVal);
                    } else if ('unique' in overlayBounds) {
                        overlayVal = overlayBounds.unique.indexOf(overlayVal);
                        style.fillColor = csc[overlayVal];
                    } else {
                        style.fillColor = "f00";
                    }
                } else {
                    style.fillColor = "f00";
                }

                style.fillOpacity = fillOpacity;
                if (feature.properties.name in lineColor) {
                    style.color = lineColor[feature.properties.name];
                } else {
                    style.color = 'white';
                }

                return style;
            }


            ,
        featureFilter: function(feature, context) {
                const {
                    overlayBounds,
                    overlayProp,
                    fillOpacity,
                    lineColor,
                    filterVals
                } = context.hideout;

                var returnFeature = true;
                if (filterVals) {
                    for (let i = 0; i < filterVals.length; i++) {
                        // Iterating through filterVals list
                        var filter = filterVals[i];
                        if (filter.name) {
                            var filterSubProps = filter.name.split(" --> ");
                            var prop_dict = feature.properties;
                            for (let j = 0; j < filterSubProps.length; j++) {
                                if (filterSubProps[j] in prop_dict) {
                                    var prop_dict = prop_dict[filterSubProps[j]];
                                    var testVal = prop_dict;
                                } else {
                                    returnFeature = returnFeature & false;
                                }
                            }
                        }

                        if (filter.range) {
                            if (typeof filter.range[0] === 'number') {
                                if (testVal < filter.range[0]) {
                                    returnFeature = returnFeature & false;
                                }
                                if (testVal > filter.range[1]) {
                                    returnFeature = returnFeature & false;
                                }
                            } else {
                                if (filter.range.includes(testVal)) {
                                    returnFeature = returnFeature & true;
                                } else {
                                    returnFeature = returnFeature & false;
                                }
                            }
                        }
                    }
                } else {
                    return returnFeature;
                }
                return returnFeature;

            }

            ,
        sendPosition: function(e, ctx) {
            ctx.setProps({
                data: e.latlng
            });
        }

    }
});