// SPDX-License-Identifier: MIT
/* Check the transport used by libssc, not just socket creation or a live PID. */
#include <glib.h>
#include <libqrtr-glib.h>
#include <string.h>

static GMainLoop *loop;
static gboolean require_ssc;
static int status = 1;

static void
ready (GObject *source, GAsyncResult *result, gpointer user_data)
{
    GError *error = NULL;
    QrtrBus *bus = qrtr_bus_new_finish (result, &error);
    gboolean found = FALSE;
    GList *item;

    (void) source;
    (void) user_data;
    if (!bus) {
        g_printerr ("QRTR bus probe failed: %s (domain=%s, code=%d)\n",
                    error ? error->message : "no error detail",
                    error ? g_quark_to_string (error->domain) : "unknown",
                    error ? error->code : -1);
        g_clear_error (&error);
        g_main_loop_quit (loop);
        return;
    }
    for (item = qrtr_bus_peek_nodes (bus); item; item = item->next) {
        if (qrtr_node_lookup_port (QRTR_NODE (item->data), 400) >= 0) {
            found = TRUE;
            break;
        }
    }
    if (require_ssc && !found) {
        g_printerr ("QRTR lookup succeeded; waiting for mock SSC service 400\n");
        status = 2;
    } else {
        g_print ("QRTR lookup succeeded%s\n", require_ssc ? "; mock SSC service 400 is registered" : "");
        status = 0;
    }
    g_object_unref (bus);
    g_main_loop_quit (loop);
}

int
main (int argc, char **argv)
{
    if (argc > 2 || (argc == 2 && strcmp (argv[1], "--ssc") != 0)) {
        g_printerr ("usage: %s [--ssc]\n", argv[0]);
        return 1;
    }
    require_ssc = argc == 2;
    loop = g_main_loop_new (NULL, FALSE);
    /* Match the initial lookup deadline in the pinned libssc client. */
    qrtr_bus_new (1000, NULL, ready, NULL);
    g_main_loop_run (loop);
    g_main_loop_unref (loop);
    return status;
}
