/* Show Me NYC — missed connections.

   Nothing is posted here automatically. Submissions arrive privately
   through the form; the owner reads each one and adds the approved ones
   below by hand (or tells an agent to).

   NEVER put in this file: last names, social handles, phone numbers,
   email addresses, or anything that identifies a person beyond what a
   stranger at the show could have seen. Never commit the submissions
   spreadsheet or anyone's contact details to this repo. */

var CONNECTIONS_META = {
  /* Link to the submission form. Leave "" until the form exists; the page
     then says submissions open soon and shows no post buttons. */
  formUrl: "https://docs.google.com/forms/d/e/1FAIpQLScqVd5eCJGufKcyrFPDJzYEbm5WxogQ6qav-zcDh_F1si_z2Q/viewform",
  /* Optional Google Forms pre-fill field names ("entry.123456"), so the
     form opens with the show or the post number already filled in. */
  prefillShow: "entry.218739778",
  prefillReply: "entry.1187751319",
  /* Posts older than this many days are hidden by the page. */
  expiresDays: 30
};

/* One entry per approved post, any order:
   {
     id: 1,                      // post number, shown as #1; never reuse one
     posted: "2026-10-05",       // the day it was approved
     night: "2026-10-04",        // the night of the show
     venue: "Elsewhere",         // as written in shows-data.js
     show: "2026-10-04-elsewhere-disco-tehran-400pm",  // show page name, or "" if unsure
     text: "You had the green jacket by the sound booth. I had the bad dancing."
   } */
var CONNECTIONS = [
];
