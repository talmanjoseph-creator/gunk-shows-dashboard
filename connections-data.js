/* Show Me NYC — missed connections settings.

   Posts and replies live in the owner's Supabase project (table
   "connections", set up by supabase/setup.sql). Visitors add them on the
   page; nothing shows until the owner approves it on mc-admin.html.

   The key below is Supabase's public "anon" / publishable key. It is meant
   to be in the page and can only do what supabase/setup.sql allows.
   NEVER put the service_role / secret key, a database password, or anyone's
   contact details in this repo. */

var CONNECTIONS_META = {
  /* Supabase project URL ("https://xxxx.supabase.co") and public anon key.
     While either is "", the page falls back to the form link below. */
  supabaseUrl: "https://duwqdwyzdorridftyxva.supabase.co",
  supabaseKey: "sb_publishable_wimklLlVfvlXBj8F1P0vjw_8pBu5RXj",
  /* Fallback only: the older Google Form, used while Supabase is not set. */
  formUrl: "https://docs.google.com/forms/d/e/1FAIpQLScqVd5eCJGufKcyrFPDJzYEbm5WxogQ6qav-zcDh_F1si_z2Q/viewform",
  /* Optional Google Forms pre-fill field names ("entry.123456"), so the
     form opens with the show or the post number already filled in. */
  prefillShow: "entry.218739778",
  prefillReply: "entry.1187751319",
  /* Posts older than this many days are hidden by the page. */
  expiresDays: 30
};

/* Fallback only: posts approved by hand in the Google Form days. Unused
   once Supabase is set. */
var CONNECTIONS = [
];
