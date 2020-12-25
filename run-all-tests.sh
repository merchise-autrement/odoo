#!/bin/bash
#
# Usage:
#
#    ./run-all-tests.sh [OPTIONS] [-- ADDONS ...]
#
# Any argument is a test addon.
#
# If you don't provide any addon, we find all directories with a
# __manifest__.py.  In this case, we don't test several blacklisted addons.
#
scriptdir=`dirname $0`

ARGS=''
ADDONS=''
while [ \! -z "$1" ]; do
    case $1 in
        --)
            shift
            TAGS="$*"
            while [ \! -z "$1" ]; do
                shift
            done
            ;;
		-i)
            shift
            if [ -z "$1" ]; then
                echo "-i requires an argument"
                exit 1;
            else
                ADDONS="$1"
            fi
            ;;
        *)
            ARGS="$ARGS $1"
            ;;
    esac
    shift
done

if [ -z "$ADDONS" ]; then
    ADDONS=`find -type f -name '__manifest__.py' | while read f; do dirname $f; done | while read d; do basename $d; done | sort -u | egrep -v '^(hw_|l10n_|theme_|auth_ldap$|auth_password_policy|document_ftp$|base_gengo$|website_gengo$|website_instantclick$|pad$|pad_project$|note_pad$|pos_cache$|pos_blackbox_be$|test_performance$|google_calendar$)' | xargs | tr " " ","`
else
    ADDONS=`echo $ADDONS | tr " " ","`
fi

if [ ! -z "$TAGS" ]; then
	ARGS="$ARGS --test-tags $TAGS"
fi

echo "Addons under test: $ADDONS"
export LANG=C.UTF-8
$scriptdir/runtests.sh -i "$ADDONS" $ARGS
