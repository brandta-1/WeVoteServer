# voter/controllers.py
# Brought to you by We Vote. Be good.
# -*- coding: UTF-8 -*-

from .models import BALLOT_ADDRESS, fetch_voter_id_from_voter_device_link, Voter, VoterAddressManager, \
    VoterDeviceLinkManager, VoterManager
from django.http import HttpResponse
from email_outbound.models import EmailManager
from follow.controllers import move_follow_entries_to_another_voter, move_organization_followers_to_another_organization
from friend.controllers import move_friend_invitations_to_another_voter, move_friends_to_another_voter
from import_export_facebook.models import FacebookManager
import json
from organization.controllers import move_organization_data_to_another_organization
from organization.models import OrganizationManager
from position.controllers import move_positions_to_another_voter
import wevote_functions.admin
from wevote_functions.functions import generate_voter_device_id, is_voter_device_id_valid, positive_value_exists

logger = wevote_functions.admin.get_logger(__name__)


# We are going to start retrieving only the ballot address
# Eventually we will want to allow saving former addresses, and mailing addresses for overseas voters
def voter_address_retrieve_for_api(voter_device_id):
    results = is_voter_device_id_valid(voter_device_id)
    if not results['success']:
        voter_address_retrieve_results = {
            'status': results['status'],
            'success': False,
            'address_found': False,
            'voter_device_id': voter_device_id,
        }
        return voter_address_retrieve_results

    voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
    if not positive_value_exists(voter_id):
        voter_address_retrieve_results = {
            'status': "VOTER_NOT_FOUND_FROM_VOTER_DEVICE_ID",
            'success': False,
            'address_found': False,
            'voter_device_id': voter_device_id,
        }
        return voter_address_retrieve_results

    voter_address_manager = VoterAddressManager()
    results = voter_address_manager.retrieve_ballot_address_from_voter_id(voter_id)

    if results['voter_address_found']:
        voter_address = results['voter_address']
        status = "VOTER_ADDRESS_RETRIEVE-ADDRESS_FOUND"

        voter_address_retrieve_results = {
            'voter_device_id': voter_device_id,
            'address_type': voter_address.address_type if voter_address.address_type else '',
            'text_for_map_search': voter_address.text_for_map_search if voter_address.text_for_map_search else '',
            'google_civic_election_id': voter_address.google_civic_election_id if voter_address.google_civic_election_id
            else 0,
            'latitude': voter_address.latitude if voter_address.latitude else '',
            'longitude': voter_address.longitude if voter_address.longitude else '',
            'normalized_line1': voter_address.normalized_line1 if voter_address.normalized_line1 else '',
            'normalized_line2': voter_address.normalized_line2 if voter_address.normalized_line2 else '',
            'normalized_city': voter_address.normalized_city if voter_address.normalized_city else '',
            'normalized_state': voter_address.normalized_state if voter_address.normalized_state else '',
            'normalized_zip': voter_address.normalized_zip if voter_address.normalized_zip else '',
            'address_found': True,
            'success': True,
            'status': status,
        }
        return voter_address_retrieve_results
    else:
        voter_address_retrieve_results = {
            'status': "VOTER_ADDRESS_NOT_FOUND",
            'success': False,
            'address_found': False,
            'voter_device_id': voter_device_id,
            'address_type': '',
            'text_for_map_search': '',
            'google_civic_election_id': 0,
            'latitude': '',
            'longitude': '',
            'normalized_line1': '',
            'normalized_line2': '',
            'normalized_city': '',
            'normalized_state': '',
            'normalized_zip': '',
        }
        return voter_address_retrieve_results


def voter_address_save_for_api(voter_device_id, voter_id, address_raw_text):
    # At this point, we have a valid voter

    voter_address_manager = VoterAddressManager()
    address_type = BALLOT_ADDRESS

    # We wrap get_or_create because we want to centralize error handling
    results = voter_address_manager.update_or_create_voter_address(voter_id, address_type, address_raw_text.strip())

    if results['success']:
        if positive_value_exists(address_raw_text):
            status = "VOTER_ADDRESS_SAVED"
        else:
            status = "VOTER_ADDRESS_EMPTY_SAVED"

        results = {
                'status': status,
                'success': True,
                'voter_device_id': voter_device_id,
                'text_for_map_search': address_raw_text,
            }
    # elif results['status'] == 'MULTIPLE_MATCHING_ADDRESSES_FOUND':
        # delete all currently matching addresses and save again
    else:
        results = {
                'status': results['status'],
                'success': False,
                'voter_device_id': voter_device_id,
                'text_for_map_search': address_raw_text,
            }
    return results


def voter_create_for_api(voter_device_id):  # voterCreate
    # If a voter_device_id isn't passed in, automatically create a new voter_device_id
    if not positive_value_exists(voter_device_id):
        voter_device_id = generate_voter_device_id()
    else:
        # If a voter_device_id is passed in that isn't valid, we want to throw an error
        results = is_voter_device_id_valid(voter_device_id)
        if not results['success']:
            return HttpResponse(json.dumps(results['json_data']), content_type='application/json')

    voter_id = 0
    voter_we_vote_id = ''
    # Make sure a voter record hasn't already been created for this
    voter_manager = VoterManager()
    results = voter_manager.retrieve_voter_from_voter_device_id(voter_device_id)
    if results['voter_found']:
        voter = results['voter']
        voter_id = voter.id
        voter_we_vote_id = voter.we_vote_id
        json_data = {
            'status': "VOTER_ALREADY_EXISTS",
            'success': True,
            'voter_device_id': voter_device_id,
            'voter_id':         voter_id,
            'voter_we_vote_id': voter_we_vote_id,
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    # Create a new voter and return the voter_device_id
    voter_manager = VoterManager()
    results = voter_manager.create_voter()

    if results['voter_created']:
        voter = results['voter']

        # Now save the voter_device_link
        voter_device_link_manager = VoterDeviceLinkManager()
        results = voter_device_link_manager.save_new_voter_device_link(voter_device_id, voter.id)

        if results['voter_device_link_created']:
            voter_device_link = results['voter_device_link']
            voter_id_found = True if voter_device_link.voter_id > 0 else False

            if voter_id_found:
                voter_id = voter.id
                voter_we_vote_id = voter.we_vote_id

    if voter_id:
        json_data = {
            'status':           "VOTER_CREATED",
            'success':          True,
            'voter_device_id':  voter_device_id,
            'voter_id':         voter_id,
            'voter_we_vote_id': voter_we_vote_id,

        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')
    else:
        json_data = {
            'status':           "VOTER_NOT_CREATED",
            'success':          False,
            'voter_device_id':  voter_device_id,
            'voter_id':         0,
            'voter_we_vote_id': '',
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')


def voter_merge_two_accounts_for_api(voter_device_id, email_secret_key, facebook_secret_key):  # voterMergeTwoAccounts
    current_voter_found = False
    email_owner_voter_found = False
    facebook_owner_voter_found = False
    new_owner_voter = Voter()
    success = False
    status = ""

    voter_device_link_manager = VoterDeviceLinkManager()
    voter_device_link_results = voter_device_link_manager.retrieve_voter_device_link(voter_device_id)
    if not voter_device_link_results['voter_device_link_found']:
        error_results = {
            'status':                   voter_device_link_results['status'],
            'success':                  False,
            'voter_device_id':          voter_device_id,
            'current_voter_found':      current_voter_found,
            'email_owner_voter_found':  email_owner_voter_found,
            'facebook_owner_voter_found': facebook_owner_voter_found,
        }
        return error_results

    # We need this below
    voter_device_link = voter_device_link_results['voter_device_link']

    voter_manager = VoterManager()
    voter_results = voter_manager.retrieve_voter_from_voter_device_id(voter_device_id)
    voter_id = voter_results['voter_id']
    if not positive_value_exists(voter_id):
        error_results = {
            'status':                   "VOTER_NOT_FOUND_FROM_VOTER_DEVICE_ID",
            'success':                  False,
            'voter_device_id':          voter_device_id,
            'current_voter_found':      current_voter_found,
            'email_owner_voter_found':  email_owner_voter_found,
            'facebook_owner_voter_found': facebook_owner_voter_found,
        }
        return error_results

    voter = voter_results['voter']
    current_voter_found = True

    if not positive_value_exists(email_secret_key) and not positive_value_exists(facebook_secret_key):
        error_results = {
            'status':                   "VOTER_MERGE_TWO_ACCOUNTS_EMAIL_SECRET_KEY_AND_FACEBOOK_SECRET_KEY_MISSING",
            'success':                  False,
            'voter_device_id':          voter_device_id,
            'current_voter_found':      current_voter_found,
            'email_owner_voter_found':  email_owner_voter_found,
            'facebook_owner_voter_found': facebook_owner_voter_found,
        }
        return error_results

    from_voter_id = 0
    from_voter_we_vote_id = ""
    to_voter_id = 0
    to_voter_we_vote_id = ""
    email_manager = EmailManager()
    if positive_value_exists(email_secret_key):
        email_results = email_manager.retrieve_email_address_object_from_secret_key(email_secret_key)
        if email_results['email_address_object_found']:
            email_address_object = email_results['email_address_object']

            email_owner_voter_results = voter_manager.retrieve_voter_by_we_vote_id(email_address_object.voter_we_vote_id)
            if email_owner_voter_results['voter_found']:
                email_owner_voter_found = True
                email_owner_voter = email_owner_voter_results['voter']

        if not email_owner_voter_found:
            error_results = {
                'status':                   "EMAIL_OWNER_VOTER_NOT_FOUND",
                'success':                  False,
                'voter_device_id':          voter_device_id,
                'current_voter_found':      current_voter_found,
                'email_owner_voter_found':  email_owner_voter_found,
                'facebook_owner_voter_found': False,
            }
            return error_results

        # Double-check they aren't the same voter account
        if voter.id == email_owner_voter.id:
            error_results = {
                'status':                   "CURRENT_VOTER_AND_EMAIL_OWNER_VOTER_ARE_SAME",
                'success':                  True,
                'voter_device_id':          voter_device_id,
                'current_voter_found':      current_voter_found,
                'email_owner_voter_found':  email_owner_voter_found,
                'facebook_owner_voter_found': False,
            }
            return error_results

        # Now we have voter (from voter_device_id) and email_owner_voter (from email_secret_key)
        # We are going to make the email_owner_voter the new master
        from_voter_id = voter.id
        from_voter_we_vote_id = voter.we_vote_id
        to_voter_id = email_owner_voter.id
        to_voter_we_vote_id = email_owner_voter.we_vote_id
        new_owner_voter = email_owner_voter
    elif positive_value_exists(facebook_secret_key):
        facebook_manager = FacebookManager()
        facebook_results = facebook_manager.retrieve_facebook_link_to_voter_from_facebook_secret_key(
            facebook_secret_key)
        if facebook_results['facebook_link_to_voter_found']:
            facebook_link_to_voter = facebook_results['facebook_link_to_voter']

            facebook_owner_voter_results = voter_manager.retrieve_voter_by_we_vote_id(
                facebook_link_to_voter.voter_we_vote_id)
            if facebook_owner_voter_results['voter_found']:
                facebook_owner_voter_found = True
                facebook_owner_voter = facebook_owner_voter_results['voter']

        if not facebook_owner_voter_found:
            error_results = {
                'status': "FACEBOOK_OWNER_VOTER_NOT_FOUND",
                'success': False,
                'voter_device_id': voter_device_id,
                'current_voter_found': current_voter_found,
                'email_owner_voter_found': False,
                'facebook_owner_voter_found': facebook_owner_voter_found,
            }
            return error_results

        auth_response_results = facebook_manager.retrieve_facebook_auth_response(voter_device_id)
        if auth_response_results['facebook_auth_response_found']:
            facebook_auth_response = auth_response_results['facebook_auth_response']

        # Double-check they aren't the same voter account
        if voter.id == facebook_owner_voter.id:
            # If here, we probably have some bad data and need to update the voter record to reflect that
            #  it is signed in with Facebook
            if auth_response_results['facebook_auth_response_found']:
                # Get the recent facebook_user_id and facebook_email
                voter_manager.update_voter_with_facebook_link_verified(
                    facebook_owner_voter,
                    facebook_auth_response.facebook_user_id, facebook_auth_response.facebook_email)

            else:
                error_results = {
                    'status': "CURRENT_VOTER_AND_EMAIL_OWNER_VOTER_ARE_SAME",
                    'success': True,
                    'voter_device_id': voter_device_id,
                    'current_voter_found': current_voter_found,
                    'email_owner_voter_found': False,
                    'facebook_owner_voter_found': facebook_owner_voter_found,
                }
                return error_results

        # ##### Make the facebook_email the primary email for facebook_owner_voter TODO DALE
        # Does facebook_owner_voter already have a primary email? If not, update it
        if not facebook_owner_voter.email_ownership_is_verified:
            if positive_value_exists(facebook_auth_response.facebook_email):
                # Check to make sure there isn't an account already using the facebook_email
                temp_voter_we_vote_id = ""
                email_results = email_manager.retrieve_primary_email_with_ownership_verified(
                    temp_voter_we_vote_id, facebook_auth_response.facebook_email)
                if not email_results['email_address_object_found']:
                    # See if an unverified email exists for this voter
                    email_address_object_we_vote_id = ""
                    email_retrieve_results = email_manager.retrieve_email_address_object(
                        facebook_auth_response.facebook_email, email_address_object_we_vote_id,
                        facebook_owner_voter.we_vote_id)
                    if email_retrieve_results['email_address_object_found']:
                        email_address_object = email_retrieve_results['email_address_object']
                        email_address_object = email_manager.update_email_address_object_to_be_verified(
                            email_address_object)
                    else:
                        email_ownership_is_verified = True
                        email_create_results = email_manager.create_email_address(
                            facebook_auth_response.facebook_email, facebook_owner_voter.we_vote_id,
                            email_ownership_is_verified)
                        if email_create_results['email_address_object_saved']:
                            email_address_object = email_create_results['email_address_object']
                    try:
                        # Attach the email_address_object to facebook_owner_voter
                        voter_manager.update_voter_email_ownership_verified(facebook_owner_voter,
                                                                            email_address_object)
                    except Exception as e:
                        # Fail silently
                        pass

        # Now we have voter (from voter_device_id) and email_owner_voter (from email_secret_key)
        # We are going to make the email_owner_voter the new master
        from_voter_id = voter.id
        from_voter_we_vote_id = voter.we_vote_id
        to_voter_id = facebook_owner_voter.id
        to_voter_we_vote_id = facebook_owner_voter.we_vote_id
        new_owner_voter = facebook_owner_voter

    # The from_voter and to_voter may both have their own linked_organization_we_vote_id
    organization_manager = OrganizationManager()
    from_voter_linked_organization_we_vote_id = voter.linked_organization_we_vote_id
    from_voter_linked_organization_id = 0
    if positive_value_exists(from_voter_linked_organization_we_vote_id):
        from_linked_organization_results = organization_manager.retrieve_organization_from_we_vote_id(
            from_voter_linked_organization_we_vote_id)
        if from_linked_organization_results['organization_found']:
            from_linked_organization = from_linked_organization_results['organization']
            from_voter_linked_organization_id = from_linked_organization.id
    to_voter_linked_organization_we_vote_id = new_owner_voter.linked_organization_we_vote_id
    to_voter_linked_organization_id = 0
    if positive_value_exists(to_voter_linked_organization_we_vote_id):
        to_linked_organization_results = organization_manager.retrieve_organization_from_we_vote_id(
            to_voter_linked_organization_we_vote_id)
        if to_linked_organization_results['organization_found']:
            to_linked_organization = to_linked_organization_results['organization']
            to_voter_linked_organization_id = to_linked_organization.id

    # If the to_voter does not have a linked_organization_we_vote_id, then we should move the from_voter's
    #  organization_we_vote_id
    if not positive_value_exists(to_voter_linked_organization_we_vote_id):
        # Use the from_voter's linked_organization_we_vote_id
        to_voter_linked_organization_we_vote_id = from_voter_linked_organization_we_vote_id
        to_voter_linked_organization_id = from_voter_linked_organization_id

    # Transfer positions from voter to new_owner_voter
    move_positions_results = move_positions_to_another_voter(
        from_voter_id, from_voter_we_vote_id,
        to_voter_id, to_voter_we_vote_id, to_voter_linked_organization_id, to_voter_linked_organization_we_vote_id)
    status += move_positions_results['status']

    if from_voter_linked_organization_we_vote_id != to_voter_linked_organization_we_vote_id:
        # If anyone is following the old voter's organization, move those followers to the new voter's organization
        move_organization_followers_results = move_organization_followers_to_another_organization(
            from_voter_linked_organization_id, from_voter_linked_organization_we_vote_id,
            to_voter_linked_organization_id, to_voter_linked_organization_we_vote_id)
        status += move_organization_followers_results['status']

        # There might be some useful information in the from_voter's organization that needs to be moved
        move_organization_results = move_organization_data_to_another_organization(
            from_voter_linked_organization_we_vote_id, to_voter_linked_organization_we_vote_id)
        status += move_organization_results['status']

        # Finally, delete the from_voter's organization
        if move_organization_results['data_transfer_complete']:
            from_organization = move_organization_results['from_organization']
            try:
                from_organization.delete()
            except Exception as e:
                # Fail silently
                pass

    # Transfer friends from voter to new_owner_voter
    move_friends_results = move_friends_to_another_voter(from_voter_we_vote_id, to_voter_we_vote_id)
    status += move_friends_results['status']

    # Transfer friend invitations from voter to email_owner_voter
    move_friend_invitations_results = move_friend_invitations_to_another_voter(
        from_voter_we_vote_id, to_voter_we_vote_id)
    status += move_friend_invitations_results['status']

    if positive_value_exists(voter.linked_organization_we_vote_id):
        # Remove the link to the organization so we don't have a future conflict
        try:
            voter.linked_organization_we_vote_id = ""
            voter.save()
        except Exception as e:
            # Fail silently
            pass

    # Transfer the organizations the from_voter is following to the new_owner_voter
    move_follow_results = move_follow_entries_to_another_voter(from_voter_id, to_voter_id, to_voter_we_vote_id)
    status += move_follow_results['status']

    # Make sure we bring over all emails from the from_voter over to the to_voter

    if positive_value_exists(voter.primary_email_we_vote_id):
        # Remove the email information so we don't have a future conflict
        try:
            voter.email = ""
            voter.primary_email_we_vote_id = ""
            voter.email_ownership_is_verified = False
            voter.save()
        except Exception as e:
            # Fail silently
            pass

    # And finally, relink the current voter_device_id to email_owner_voter
    update_link_results = voter_device_link_manager.update_voter_device_link(voter_device_link, new_owner_voter)
    if update_link_results['voter_device_link_updated']:
        success = True
        status += "MERGE_TWO_ACCOUNTS_VOTER_DEVICE_LINK_UPDATED"

    results = {
        'status': status,
        'success': success,
        'voter_device_id': voter_device_id,
        'current_voter_found': current_voter_found,
        'email_owner_voter_found': email_owner_voter_found,
        'facebook_owner_voter_found': facebook_owner_voter_found,
    }

    return results


def voter_photo_save_for_api(voter_device_id, facebook_profile_image_url_https, facebook_photo_variable_exists):
    facebook_profile_image_url_https = facebook_profile_image_url_https.strip()

    device_id_results = is_voter_device_id_valid(voter_device_id)
    if not device_id_results['success']:
        results = {
                'status': device_id_results['status'],
                'success': False,
                'voter_device_id': voter_device_id,
                'facebook_profile_image_url_https': facebook_profile_image_url_https,
            }
        return results

    if not facebook_photo_variable_exists:
        results = {
                'status': "MISSING_VARIABLE-AT_LEAST_ONE_PHOTO",
                'success': False,
                'voter_device_id': voter_device_id,
                'facebook_profile_image_url_https': facebook_profile_image_url_https,
            }
        return results

    voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
    if voter_id < 0:
        results = {
            'status': "VOTER_NOT_FOUND_FROM_DEVICE_ID",
            'success': False,
            'voter_device_id': voter_device_id,
            'facebook_profile_image_url_https': facebook_profile_image_url_https,
        }
        return results

    # At this point, we have a valid voter

    voter_manager = VoterManager()
    results = voter_manager.update_voter_photos(voter_id,
                                                facebook_profile_image_url_https, facebook_photo_variable_exists)

    if results['success']:
        if positive_value_exists(facebook_profile_image_url_https):
            status = "VOTER_FACEBOOK_PHOTO_SAVED"
        else:
            status = "VOTER_PHOTOS_EMPTY_SAVED"

        results = {
                'status': status,
                'success': True,
                'voter_device_id': voter_device_id,
                'facebook_profile_image_url_https': facebook_profile_image_url_https,
            }

    else:
        results = {
                'status': results['status'],
                'success': False,
                'voter_device_id': voter_device_id,
                'facebook_profile_image_url_https': facebook_profile_image_url_https,
            }
    return results


def voter_retrieve_for_api(voter_device_id):  # voterRetrieve
    """
    Used by the api
    :param voter_device_id:
    :return:
    """
    voter_manager = VoterManager()
    voter_id = 0
    voter_created = False

    if positive_value_exists(voter_device_id):
        # If a voter_device_id is passed in that isn't valid, we want to throw an error
        device_id_results = is_voter_device_id_valid(voter_device_id)
        if not device_id_results['success']:
            json_data = {
                    'status':           device_id_results['status'],
                    'success':          False,
                    'voter_device_id':  voter_device_id,
                    'voter_created':    False,
                    'voter_found':      False,
                }
            return json_data

        voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
        if not positive_value_exists(voter_id):
            json_data = {
                'status':           "VOTER_NOT_FOUND_FROM_DEVICE_ID",
                'success':          False,
                'voter_device_id':  voter_device_id,
                'voter_created':    False,
                'voter_found':      False,
            }
            return json_data
    else:
        # If a voter_device_id isn't passed in, automatically create a new voter_device_id and voter
        voter_device_id = generate_voter_device_id()

        # We make sure a voter record hasn't already been created for this new voter_device_id, so we don't create a
        # security hole by giving a new person access to an existing account. This should never happen because it is
        # so unlikely that we will ever generate an existing voter_device_id with generate_voter_device_id.
        existing_voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
        if existing_voter_id:
            json_data = {
                'status':           "VOTER_ALREADY_EXISTS_BUT_ACCESS_RESTRICTED",
                'success':          False,
                'voter_device_id':  voter_device_id,
                'voter_created':    False,
                'voter_found':      False,
            }
            return json_data

        results = voter_manager.create_voter()

        if results['voter_created']:
            voter = results['voter']

            # Now save the voter_device_link
            voter_device_link_manager = VoterDeviceLinkManager()
            results = voter_device_link_manager.save_new_voter_device_link(voter_device_id, voter.id)

            if results['voter_device_link_created']:
                voter_device_link = results['voter_device_link']
                voter_id_found = True if voter_device_link.voter_id > 0 else False

                if voter_id_found:
                    voter_id = voter_device_link.voter_id
                    voter_created = True

        if not positive_value_exists(voter_id):
            json_data = {
                'status':           "VOTER_NOT_FOUND_AFTER_BEING_CREATED",
                'success':          False,
                'voter_device_id':  voter_device_id,
                'voter_created':    False,
                'voter_found':      False,
            }
            return json_data

    # At this point, we should have a valid voter_id
    results = voter_manager.retrieve_voter_by_id(voter_id)
    if results['voter_found']:
        voter = results['voter']

        if voter_created:
            status = 'VOTER_CREATED'
        else:
            status = 'VOTER_FOUND'
        json_data = {
            'status':                           status,
            'success':                          True,
            'voter_device_id':                  voter_device_id,
            'voter_created':                    voter_created,
            'voter_found':                      True,
            'we_vote_id':                       voter.we_vote_id,
            'facebook_id':                      voter.facebook_id,
            'email':                            voter.email,
            'facebook_email':                   voter.facebook_email,
            'facebook_profile_image_url_https': voter.facebook_profile_image_url_https,
            'full_name':                        voter.get_full_name(),
            'first_name':                       voter.first_name,
            'last_name':                        voter.last_name,
            'twitter_screen_name':              voter.twitter_screen_name,
            'signed_in_personal':               voter.signed_in_personal(),
            'signed_in_facebook':               voter.signed_in_facebook(),
            'signed_in_google':                 voter.signed_in_google(),
            'signed_in_twitter':                voter.signed_in_twitter(),
            'signed_in_with_email':             voter.signed_in_with_email(),
            'has_valid_email':                  voter.has_valid_email(),
            'has_data_to_preserve':             voter.has_data_to_preserve(),
            'has_email_with_verified_ownership':    voter.has_email_with_verified_ownership(),
            'linked_organization_we_vote_id':   voter.linked_organization_we_vote_id,
            'voter_photo_url':                  voter.voter_photo_url(),
        }
        return json_data

    else:
        status = results['status']
        json_data = {
            'status':                           status,
            'success':                          False,
            'voter_device_id':                  voter_device_id,
            'voter_created':                    False,
            'voter_found':                      False,
            'we_vote_id':                       '',
            'facebook_id':                      '',
            'email':                            '',
            'facebook_email':                   '',
            'facebook_profile_image_url_https': '',
            'full_name':                        '',
            'first_name':                       '',
            'last_name':                        '',
            'twitter_screen_name':              '',
            'signed_in_personal':               False,
            'signed_in_facebook':               False,
            'signed_in_google':                 False,
            'signed_in_twitter':                False,
            'signed_in_with_email':             False,
            'has_valid_email':                  False,
            'has_data_to_preserve':             False,
            'has_email_with_verified_ownership':    False,
            'linked_organization_we_vote_id':   '',
            'voter_photo_url':                  '',
        }
        return json_data


def voter_retrieve_list_for_api(voter_device_id):
    """
    This is used for voterExportView
    :param voter_device_id:
    :return:
    """
    results = is_voter_device_id_valid(voter_device_id)
    if not results['success']:
        results2 = {
            'success': False,
            'json_data': results['json_data'],
        }
        return results2

    voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
    if voter_id > 0:
        voter_manager = VoterManager()
        results = voter_manager.retrieve_voter_by_id(voter_id)
        if results['voter_found']:
            voter_id = results['voter_id']
    else:
        # If we are here, the voter_id could not be found from the voter_device_id
        json_data = {
            'status': "VOTER_NOT_FOUND_FROM_DEVICE_ID",
            'success': False,
            'voter_device_id': voter_device_id,
        }
        results = {
            'success': False,
            'json_data': json_data,
        }
        return results

    if voter_id:
        voter_list = Voter.objects.all()
        voter_list = voter_list.filter(id=voter_id)

        if len(voter_list):
            results = {
                'success': True,
                'voter_list': voter_list,
            }
            return results

    # Trying to mimic the Google Civic error codes scheme
    errors_list = [
        {
            'domain':  "TODO global",
            'reason':  "TODO reason",
            'message':  "TODO Error message here",
            'locationType':  "TODO Error message here",
            'location':  "TODO location",
        }
    ]
    error_package = {
        'errors':   errors_list,
        'code':     400,
        'message':  "Error message here",
    }
    json_data = {
        'error': error_package,
        'status': "VOTER_ID_COULD_NOT_BE_RETRIEVED",
        'success': False,
        'voter_device_id': voter_device_id,
    }
    results = {
        'success': False,
        'json_data': json_data,
    }
    return results


def voter_sign_out_for_api(voter_device_id, sign_out_all_devices=False):  # voterSignOut
    voter_device_link_manager = VoterDeviceLinkManager()
    if sign_out_all_devices:
        results = voter_device_link_manager.delete_all_voter_device_links(voter_device_id)
    else:
        results = voter_device_link_manager.delete_voter_device_link(voter_device_id)

    results = {
        'success':  results['success'],
        'status':   results['status'],
    }
    return results
