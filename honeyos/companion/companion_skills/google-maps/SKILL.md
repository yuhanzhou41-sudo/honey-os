---
name: google-maps
description: Use Google Maps for nearby or nearest businesses, restaurants, salons, shops, ratings, current hours, photos, official links, and navigation. Trigger whenever the user asks where to go or what is near a location.
metadata:
  honeyos:
    tags: [google-maps, places, nearby, local-life, navigation]
    category: lifestyle
    requires_toolsets: [local_life]
---

# Google Maps

For nearby or nearest places, call `google_maps_search` directly with the user's
business need as `query` and their address, office, landmark, neighborhood, or
city as `near`. The tool calls Google Places API and needs no terminal approval.

Do not use `execute_code`, `terminal`, Overpass, OpenStreetMap, the old `maps`
Skill, or `web_search` before this tool. Only fall back to general public web
search when the tool explicitly returns `fallback_required: true`. If results
exist but `photo_fallback_required: true`, one targeted Yelp search is allowed
to add a current Yelp rating and a Yelp business-page rich preview; never scrape
or invent an image URL.

## Response

- For every successful local-business request, return the useful local-life
  package by default; the user does not need to ask for each field: rating,
  distance when the API returned one, a tappable Google Maps/directions link,
  and one real Google business photo when `image_path` is available.
- Lead with one recommendation and the strongest reasons: location, rating,
  review count, open status, specialty, or price.
- Include at most two alternatives when useful.
- Put each returned `maps_url` or `directions_url` on its own line so iMessage
  can create a tappable rich preview.
- In iMessage, a Google Maps or Yelp URL on its own line is part of the output
  contract: HoneyOS turns it into a native tappable rich-link shop card rather
  than leaving a naked URL inside the prose bubble.
- If `image_path` is present, include exactly one `MEDIA:<image_path>` line so
  iMessage sends the Google business photo as a native image attachment.
- If Google returns no photo or no calculable distance, say so briefly instead
  of silently omitting it or inventing one.
- Call `google_maps_search` as a direct tool. Never wrap it in `tool_call` or
  retrieve the answer from conversational memory; memory may supply the user's
  location, but current business facts must come from Google Places.
- Include the official or booking link when returned. Never invent a photo,
  distance, opening status, rating, or link.
- Do not expose API keys, implementation details, tool names, code, or approval
  instructions to the user.
