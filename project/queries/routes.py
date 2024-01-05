import sqlite3
import traceback

from flask import jsonify, request, make_response
from flasgger import swag_from

from . import midas_blueprint
from . import DB_LOCATION

# TODO: Better errors for identifying malformed queries

def connect_to_db():
    try:
        conn = sqlite3.connect(DB_LOCATION)
        conn.row_factory=sqlite3.Row
        print('connection successful')
        return conn
    except sqlite3.Error as e:
        tb = traceback.format_exc()
        print(e)
        print(tb)


@midas_blueprint.route('/searchData/', methods=['GET'])
@swag_from('../swagger_docs/getSearchData.yml')
def get_search_data():
    searches = [x.lower() for x in request.json['categories']]
    if not set(searches).issubset(['papers', 'organizations', 'people', 'grants', 'keywords']):
        return make_response("Invalid value in search requests", 400)
    
    conn = connect_to_db()
    cur = conn.cursor()
    response = {}

    if 'papers' in searches:
        response.update(get_full_paper_list(cur))
    if 'organizations' in searches:
        response.update(get_full_org_list(cur))
    if 'people' in searches:
        response.update(get_full_people_list(cur))
    if 'grants' in searches:
        response.update(get_full_grant_list(cur))
    if 'keywords' in searches:
        response.update(get_full_keyword_list(cur))

    # response = {**papers, **orgs, **authors, **grants, **terms}
    return make_response(jsonify(response), 200)

def get_full_paper_list(cur):
    q = 'SELECT DISTINCT paperid, title FROM pdetails'
    cur.execute(q)
    rows = cur.fetchall()
    papers = {'papers': [{'id': x['paperid'], 'name': x['title']} for x in rows]}
    return papers


def get_full_org_list(cur):
    q = 'SELECT DISTINCT orgid, org_name FROM odetails'
    cur.execute(q)
    rows = cur.fetchall()
    orgs = {'orgs': [{'id': x['orgid'], 'name': x['org_name']} for x in rows]}
    return orgs


def get_full_people_list(cur):
    q = 'SELECT DISTINCT authorid, author_name FROM adetails'
    cur.execute(q)
    rows = cur.fetchall()
    people = {'people': [{'id': x['authorid'], 'name': x['author_name']} for x in rows]}
    return people


def get_full_grant_list(cur):
    q = 'SELECT DISTINCT grantid, title FROM gdetails'
    cur.execute(q)
    rows = cur.fetchall()
    grants = {'grants': [{'id': x['grantid'], 'name': x['title']} for x in rows]}
    return grants


def get_full_keyword_list(cur):
    q = 'SELECT DISTINCT term FROM pcount'
    cur.execute(q)
    rows = cur.fetchall()
    terms = {'keywords': [x['term'] for x in rows]}
    return terms


@midas_blueprint.route('/intersection/papers/', methods=['GET'])
@swag_from('../swagger_docs/paperOverlap.yml')
def get_paper_list():
    if not set(request.json.keys()).issubset(['authors', 'grants', 'keywords', 'orgs', 'publicationDateRange']):
        return make_response("Invalid value in search requests", 400)

    conn = connect_to_db()
    cur = conn.cursor()

    withAuthors = False
    withOrgs = False
    withKeywords = False
    withGrants = False
    withDates = False

    if 'authors' in request.json.keys():
        withAuthors = True
    if 'orgs' in request.json.keys():
        withOrgs = True
    if 'keywords' in request.json.keys():
        withKeywords = True
    if 'grants' in request.json.keys():
        withGrants = True
    if 'publicationDateRange' in request.json.keys():
        withDates = True

    q = ''
    formatted_ids = []
    if withDates:
        q = 'SELECT DISTINCT paperid FROM pdetails WHERE '
        if 'start' in request.json['publicationDateRange'].keys():
            if 'end' in request.json['publicationDateRange'].keys():
                q += 'year BETWEEN ? AND ?'
                formatted_ids.extend([request.json['publicationDateRange']['start'],request.json['publicationDateRange']['end']])
            else:
                q += 'year >= ?'
                formatted_ids.extend([request.json['publicationDateRange']['start']])
        elif 'end' in request.json['publicationDateRange'].keys():
            q += 'year <= ?'
            formatted_ids.extend([request.json['publicationDateRange']['end']])
    if withAuthors:
        for author in request.json['authors']:
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT paperid FROM p2au WHERE authorid=?'
            formatted_ids.append(author)
    if withOrgs:
        for org in request.json['orgs']:
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT paperid FROM p2org WHERE orgid=?'
            formatted_ids.append(org)
    if withKeywords:
        for term in request.json['keywords']:
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT paperid FROM pcount WHERE term=?'
            formatted_ids.append(term)
    if withGrants:
        if 'grantList' in request.json['grants'].keys():
            for grant in request.json['grants']['grantList']:
                if len(q) != 0:
                    q += ' INTERSECT '
                q += 'SELECT DISTINCT paperid FROM g2p WHERE grantid=?'
                formatted_ids.append(grant)
        if 'dates' in request.json['grants'].keys():
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT paperid FROM g2p WHERE grantid IN (SELECT DISTINCT grantid FROM gdetails WHERE '
            if 'start' in request.json['grants']['dates'].keys():
                if 'end' in request.json['grants']['dates'].keys():
                    q += '(startdate BETWEEN ? AND ?) OR (enddate BETWEEN ? AND ?)'
                    formatted_ids.extend([request.json['grants']['dates']['start'],request.json['grants']['dates']['end'],
                                          request.json['grants']['dates']['start'],request.json['grants']['dates']['end']])
                else:
                    q += 'startdate >= ? OR enddate >= ?'
                    formatted_ids.extend([request.json['grants']['dates']['start'], request.json['grants']['dates']['start']])
            elif 'end' in request.json['grants']['dates'].keys():
                q += 'startdate <= ? OR enddate <= ?'
                formatted_ids.extend([request.json['grants']['dates']['end'], request.json['grants']['dates']['end']])
            q += ')'
    
    final_q = 'SELECT DISTINCT paperid, title FROM pdetails WHERE paperid IN (' + q + ')'
    print(('='*5) + 'query' + ('='*5) + '\n' + q)
    cur.execute(final_q, tuple(formatted_ids))
    rows = cur.fetchall()
    papers = [{'id': x['paperid'], 'name': x['title']} for x in rows]
    return make_response(jsonify(papers), 200) 

@midas_blueprint.route('/intersection/grants/', methods=['GET'])
@swag_from('../swagger_docs/grantOverlap.yml')
def get_grant_list():
    if not set(request.json.keys()).issubset(['people', 'papers', 'keywords', 'orgs', 'grantDateRange']):
        return make_response("Invalid value in search requests", 400)
    conn = connect_to_db()
    cur = conn.cursor()

    withPeople = False
    withOrgs = False # Not in powerpoint but seems doable
    withKeywords = False
    withPapers = False
    withDates = False

    if 'people' in request.json.keys():
        withPeople = True
    if 'orgs' in request.json.keys():
        withOrgs = True
    if 'keywords' in request.json.keys():
        withKeywords = True
    if 'papers' in request.json.keys():
        withPapers = True
    if 'grantDateRange' in request.json.keys():
        withDates = True

    q = ''
    formatted_ids = []
    if withDates:
        q = 'SELECT DISTINCT grantid FROM gdetails WHERE '
        if 'start' in request.json['grantDateRange'].keys():
            if 'end' in request.json['grantDateRange'].keys():
                q += '(startdate BETWEEN ? AND ?) OR (enddate BETWEEN ? AND ?)'
                formatted_ids.extend([request.json['grantDateRange']['start'],request.json['grantDateRange']['end'],
                                      request.json['grantDateRange']['start'],request.json['grantDateRange']['end']])
            else:
                q += 'startdate >= ? OR enddate >= ?'
                formatted_ids.extend([request.json['grantDateRange']['start'], request.json['grantDateRange']['start']])
        elif 'end' in request.json['grantDateRange'].keys():
            q += 'startdate <= ? OR enddate <= ?'
            formatted_ids.extend([request.json['grantDateRange']['end'], request.json['grantDateRange']['end']])
    if withPeople:
        for author in request.json['people']:
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT grantid FROM g2a WHERE grantid=?'
            formatted_ids.append(author)
    if withOrgs:
        for org in request.json['orgs']:
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT grantid FROM g2p a JOIN p2org b ON a.paperid=b.paperid WHERE orgid=?'
            formatted_ids.append(org)
    if withKeywords:
        for term in request.json['keywords']:
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT grantid FROM g2p a JOIN pcount b ON a.paperid=b.paperid WHERE term=?'
            formatted_ids.append(term)
    if withPapers:
        if 'paperList' in request.json['papers'].keys():
            for paper in request.json['papers']['paperList']:
                if len(q) != 0:
                    q += ' INTERSECT '
                q += 'SELECT DISTINCT grantid FROM g2p WHERE paperid=?'
                formatted_ids.append(paper)
        if 'dates' in request.json['papers'].keys():
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT grantid FROM g2p WHERE paperid IN (SELECT paperid FROM pdetails WHERE '
            if 'start' in request.json['papers']['dates'].keys():
                if 'end' in request.json['papers']['dates'].keys():
                    q += 'year BETWEEN ? AND ?'
                    formatted_ids.extend([request.json['papers']['dates']['start'],request.json['papers']['dates']['end']])
                else:
                    q += 'year >= ?'
                    formatted_ids.extend([request.json['papers']['dates']['start']])
            elif 'end' in request.json['papers']['dates'].keys():
                q += 'year <= ?'
                formatted_ids.extend([request.json['papers']['dates']['end']])
            q += ')'
    
    final_q = 'SELECT DISTINCT grantid, title FROM gdetails WHERE grantid IN (' + q + ')'
    print(('='*5) + 'query' + ('='*5) + '\n' + q)
    cur.execute(final_q, tuple(formatted_ids))
    rows = cur.fetchall()
    grants = [{'id': x['grantid'], 'name': x['title']} for x in rows]
    return make_response(jsonify(grants), 200) 

@midas_blueprint.route('/intersection/people/', methods=['GET'])
@swag_from('../swagger_docs/peopleOverlap.yml')
def get_people_list():
    if not set(request.json.keys()).issubset(['coauthors', 'grants', 'keywords', 'orgs', 'papers']):
        return make_response("Invalid value in search requests", 400)
    print('##' * 20)
    conn = connect_to_db()
    cur = conn.cursor()

    withAuthors = False
    withPapers = False # Not in powerpoint but seems doable
    withOrg = False
    withKeywords = False
    withGrants = False

    if 'coauthors' in request.json.keys():
        withAuthors = True
    if 'papers' in request.json.keys():
        withPapers = True
    if 'org' in request.json.keys():
        withOrg = True
    if 'keywords' in request.json.keys():
        withKeywords = True
    if 'grants' in request.json.keys():
        withGrants = True

    q = ''
    formatted_ids = []
    if withAuthors:
        for author in request.json['coauthors']:
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT authorid FROM p2au WHERE paperid IN (SELECT DISTINCT paperid FROM p2au WHERE authorid=?)'
            formatted_ids.append(author)
    if withPapers:
        if 'paperList' in request.json['papers'].keys():
            for paper in request.json['papers']['paperList']:
                if len(q) != 0:
                    q += ' INTERSECT '
                q += 'SELECT DISTINCT authorid FROM g2a WHERE paperid=?'
                formatted_ids.append(paper)
        if 'dates' in request.json['papers'].keys():
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT authorid FROM p2au WHERE paperid IN (SELECT paperid FROM pdetails WHERE '
            if 'start' in request.json['papers']['dates'].keys():
                if 'end' in request.json['papers']['dates'].keys():
                    q += 'year BETWEEN ? AND ?'
                    formatted_ids.extend([request.json['papers']['dates']['start'],request.json['papers']['dates']['end']])
                else:
                    q += 'year >= ?'
                    formatted_ids.extend([request.json['papers']['dates']['start']])
            elif 'end' in request.json['papers']['dates'].keys():
                q += 'year <= ?'
                formatted_ids.extend([request.json['papers']['dates']['end']])
            q += ')'
    if withOrg:
        if len(q) != 0:
            q += ' INTERSECT '
        q += 'SELECT DISTINCT authorid FROM adetails WHERE orgid=?'
        formatted_ids.append(request.json['org'])
    if withKeywords:
        for term in request.json['keywords']:
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT authorid FROM p2au WHERE paperid IN (SELECT DISTINCT paperid FROM pcount WHERE term=?)'
            formatted_ids.append(term)
    if withGrants:
        if 'grantList' in request.json['grants'].keys():
            for grant in request.json['grants']['grantList']:
                if len(q) != 0:
                    q += ' INTERSECT '
                q += 'SELECT DISTINCT authorid FROM g2a WHERE grantid=?'
                formatted_ids.append(grant)
        if 'dates' in request.json['grants'].keys():
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT authorid FROM g2a WHERE grantid IN (SELECT DISTINCT grantid FROM gdetails WHERE '
            if 'start' in request.json['grants']['dates'].keys():
                if 'end' in request.json['grants']['dates'].keys():
                    q += '(startdate BETWEEN ? AND ?) OR (enddate BETWEEN ? AND ?)'
                    formatted_ids.extend([request.json['grants']['dates']['start'],request.json['grants']['dates']['end'],
                                          request.json['grants']['dates']['start'],request.json['grants']['dates']['end']])
                else:
                    q += 'startdate >= ? OR enddate >= ?'
                    formatted_ids.extend([request.json['grants']['dates']['start'], request.json['grants']['dates']['start']])
            elif 'end' in request.json['grants']['dates'].keys():
                q += 'startdate <= ? OR enddate <= ?'
                formatted_ids.extend([request.json['grants']['dates']['end'], request.json['grants']['dates']['end']])
            q += ')'
    
    final_q = 'SELECT DISTINCT authorid, author_name FROM adetails WHERE authorid IN (' + q + ')'
    print(('='*5) + 'query' + ('='*5) + '\n' + q)
    cur.execute(final_q, tuple(formatted_ids))
    rows = cur.fetchall()
    people = [{'id': x['authorid'], 'name': x['author_name']} for x in rows]
    return make_response(jsonify(people), 200) 

@midas_blueprint.route('/intersection/orgs/', methods=['GET'])
@swag_from('../swagger_docs/orgOverlap.yml')
def get_org_list():
    if not set(request.json.keys()).issubset(['person', 'grants', 'keywords', 'papers']):
        return make_response("Invalid value in search requests", 400)
    conn = connect_to_db()
    cur = conn.cursor()

    withPerson = False
    withKeywords = False
    withGrants = False
    withPapers = False

    if 'person' in request.json.keys():
        withPerson = True
    if 'keywords' in request.json.keys():
        withKeywords = True
    if 'grants' in request.json.keys():
        withGrants = True
    if 'papers' in request.json.keys():
        withPapers = True

    q = ''
    formatted_ids = []
    if withPerson:
        q += 'SELECT DISTINCT orgid FROM adetails WHERE authorid=?'
        formatted_ids.append(request.json['person'])
    if withKeywords:
        for term in request.json['keywords']:
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT orgid FROM p2org WHERE paperid IN (SELECT DISTINCT paperid FROM pcount WHERE term=?)'
            formatted_ids.append(term)
    if withGrants:
        if 'grantList' in request.json['grants'].keys():
            for grant in request.json['grants']['grantList']:
                if len(q) != 0:
                    q += ' INTERSECT '
                q += 'SELECT DISTINCT orgid FROM adetails WHERE authorid IN (SELECT DISTINCT authorid FROM g2a WHERE grantid=?)'
                formatted_ids.append(grant)
        if 'dates' in request.json['grants'].keys():
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT orgid FROM adetails WHERE authorid IN (SELECT DISTINCT authorid FROM g2a WHERE grantid IN (SELECT DISTINCT grantid FROM gdetails WHERE '
            if 'start' in request.json['grants']['dates'].keys():
                if 'end' in request.json['grants']['dates'].keys():
                    q += '(startdate BETWEEN ? AND ?) OR (enddate BETWEEN ? AND ?)'
                    formatted_ids.extend([request.json['grants']['dates']['start'],request.json['grants']['dates']['end'],
                                          request.json['grants']['dates']['start'],request.json['grants']['dates']['end']])
                else:
                    q += 'startdate >= ? OR enddate >= ?'
                    formatted_ids.extend([request.json['grants']['dates']['start'], request.json['grants']['dates']['start']])
            elif 'end' in request.json['grants']['dates'].keys():
                q += 'startdate <= ? OR enddate <= ?'
                formatted_ids.extend([request.json['grants']['dates']['end'], request.json['grants']['dates']['end']])
            q += '))'
    if withPapers:
        if 'paperList' in request.json['papers'].keys():
            for paper in request.json['papers']['paperList']:
                if len(q) != 0:
                    q += ' INTERSECT '
                q += 'SELECT DISTINCT orgid FROM p2org WHERE paperid=?'
                formatted_ids.append(paper)
        if 'dates' in request.json['papers'].keys():
            if len(q) != 0:
                q += ' INTERSECT '
            q += 'SELECT DISTINCT orgid FROM p2org WHERE paperid IN (SELECT paperid FROM pdetails WHERE '
            if 'start' in request.json['papers']['dates'].keys():
                if 'end' in request.json['papers']['dates'].keys():
                    q += 'year BETWEEN ? AND ?'
                    formatted_ids.extend([request.json['papers']['dates']['start'],request.json['papers']['dates']['end']])
                else:
                    q += 'year >= ?'
                    formatted_ids.extend([request.json['papers']['dates']['start']])
            elif 'end' in request.json['papers']['dates'].keys():
                q += 'year <= ?'
                formatted_ids.extend([request.json['papers']['dates']['end']])
            q += ')'
    
    final_q = 'SELECT DISTINCT orgid, org_name FROM odetails WHERE orgid IN (' + q + ')'
    print(('='*5) + 'query' + ('='*5) + '\n' + q)
    cur.execute(final_q, tuple(formatted_ids))
    rows = cur.fetchall()
    orgs = [{'id': x['orgid'], 'name': x['org_name']} for x in rows]
    return make_response(jsonify(orgs), 200) 