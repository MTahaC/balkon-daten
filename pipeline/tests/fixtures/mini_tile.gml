<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<!--
  Hand-written CityGML 1.0 test fixture in the structure of the NRW LoD2 tiles
  (namespaces, srsName, boundedBy surfaces, BuildingParts). Coordinates lie in
  tile 356_5644 (EPSG:25832), heights in DHHN2016. Only the surfaces the
  pipeline reads are included, plus one WallSurface that must be ignored.
  Ground rings are clockwise seen from above, as in the real data (their
  normals point down).
-->
<core:CityModel xmlns:bldg="http://www.opengis.net/citygml/building/1.0" xmlns:gml="http://www.opengis.net/gml" xmlns:core="http://www.opengis.net/citygml/1.0">
  <gml:name>mini_tile</gml:name>
  <gml:boundedBy>
    <gml:Envelope srsName="urn:adv:crs:ETRS89_UTM32*DE_DHHN2016_NH">
      <gml:lowerCorner srsDimension="3">356000.0 5644000.0 50.0</gml:lowerCorner>
      <gml:upperCorner srsDimension="3">357000.0 5645000.0 90.0</gml:upperCorner>
    </gml:Envelope>
  </gml:boundedBy>

  <!-- 10 x 10 m flat roof box, 12 m high -->
  <core:cityObjectMember>
    <bldg:Building gml:id="B_FLAT">
      <bldg:function>31001_1000</bldg:function>
      <bldg:roofType>1000</bldg:roofType>
      <bldg:measuredHeight uom="urn:adv:uom:m">12.0</bldg:measuredHeight>
      <bldg:boundedBy>
        <bldg:WallSurface>
          <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
            <gml:posList srsDimension="3">356010 5644010 50 356020 5644010 50 356020 5644010 62 356010 5644010 62 356010 5644010 50</gml:posList>
          </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
        </bldg:WallSurface>
      </bldg:boundedBy>
      <bldg:boundedBy>
        <bldg:RoofSurface>
          <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
            <gml:posList srsDimension="3">356010 5644010 62 356020 5644010 62 356020 5644020 62 356010 5644020 62 356010 5644010 62</gml:posList>
          </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
        </bldg:RoofSurface>
      </bldg:boundedBy>
      <bldg:boundedBy>
        <bldg:GroundSurface>
          <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
            <gml:posList srsDimension="3">356010 5644010 50 356010 5644020 50 356020 5644020 50 356020 5644010 50 356010 5644010 50</gml:posList>
          </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
        </bldg:GroundSurface>
      </bldg:boundedBy>
    </bldg:Building>
  </core:cityObjectMember>

  <!-- 10 x 8 m gable roof, ridge east-west at y = 5644104: eave 6 m, ridge 10 m -->
  <core:cityObjectMember>
    <bldg:Building gml:id="B_GABLE">
      <bldg:roofType>3100</bldg:roofType>
      <bldg:measuredHeight uom="urn:adv:uom:m">10.0</bldg:measuredHeight>
      <bldg:boundedBy>
        <bldg:RoofSurface>
          <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
            <gml:posList srsDimension="3">356100 5644100 56 356110 5644100 56 356110 5644104 60 356100 5644104 60 356100 5644100 56</gml:posList>
          </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
        </bldg:RoofSurface>
      </bldg:boundedBy>
      <bldg:boundedBy>
        <bldg:RoofSurface>
          <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
            <gml:posList srsDimension="3">356100 5644104 60 356110 5644104 60 356110 5644108 56 356100 5644108 56 356100 5644104 60</gml:posList>
          </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
        </bldg:RoofSurface>
      </bldg:boundedBy>
      <bldg:boundedBy>
        <bldg:GroundSurface>
          <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
            <gml:posList srsDimension="3">356100 5644100 50 356100 5644108 50 356110 5644108 50 356110 5644100 50 356100 5644100 50</gml:posList>
          </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
        </bldg:GroundSurface>
      </bldg:boundedBy>
    </bldg:Building>
  </core:cityObjectMember>

  <!-- Church-like building: 20 x 10 m nave (15 m) + 5 x 5 m tower (40 m) as parts -->
  <core:cityObjectMember>
    <bldg:Building gml:id="B_PARTS">
      <bldg:function>31001_3040</bldg:function>
      <bldg:consistsOfBuildingPart>
        <bldg:BuildingPart gml:id="B_PARTS_NAVE">
          <bldg:roofType>1000</bldg:roofType>
          <bldg:measuredHeight uom="urn:adv:uom:m">15.0</bldg:measuredHeight>
          <bldg:boundedBy>
            <bldg:RoofSurface>
              <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
                <gml:posList srsDimension="3">356200 5644200 65 356220 5644200 65 356220 5644210 65 356200 5644210 65 356200 5644200 65</gml:posList>
              </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
            </bldg:RoofSurface>
          </bldg:boundedBy>
          <bldg:boundedBy>
            <bldg:GroundSurface>
              <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
                <gml:posList srsDimension="3">356200 5644200 50 356200 5644210 50 356220 5644210 50 356220 5644200 50 356200 5644200 50</gml:posList>
              </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
            </bldg:GroundSurface>
          </bldg:boundedBy>
        </bldg:BuildingPart>
      </bldg:consistsOfBuildingPart>
      <bldg:consistsOfBuildingPart>
        <bldg:BuildingPart gml:id="B_PARTS_TOWER">
          <bldg:roofType>1000</bldg:roofType>
          <bldg:measuredHeight uom="urn:adv:uom:m">40.0</bldg:measuredHeight>
          <bldg:boundedBy>
            <bldg:RoofSurface>
              <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
                <gml:posList srsDimension="3">356220 5644202 90 356225 5644202 90 356225 5644207 90 356220 5644207 90 356220 5644202 90</gml:posList>
              </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
            </bldg:RoofSurface>
          </bldg:boundedBy>
          <bldg:boundedBy>
            <bldg:GroundSurface>
              <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
                <gml:posList srsDimension="3">356220 5644202 50 356220 5644207 50 356225 5644207 50 356225 5644202 50 356220 5644202 50</gml:posList>
              </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
            </bldg:GroundSurface>
          </bldg:boundedBy>
        </bldg:BuildingPart>
      </bldg:consistsOfBuildingPart>
    </bldg:Building>
  </core:cityObjectMember>

  <!-- 30 x 30 m block with a 10 x 10 m courtyard (interior ring), 20 m -->
  <core:cityObjectMember>
    <bldg:Building gml:id="B_COURT">
      <bldg:roofType>1000</bldg:roofType>
      <bldg:boundedBy>
        <bldg:RoofSurface>
          <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon>
            <gml:exterior><gml:LinearRing>
              <gml:posList srsDimension="3">356300 5644300 70 356330 5644300 70 356330 5644330 70 356300 5644330 70 356300 5644300 70</gml:posList>
            </gml:LinearRing></gml:exterior>
            <gml:interior><gml:LinearRing>
              <gml:posList srsDimension="3">356310 5644310 70 356310 5644320 70 356320 5644320 70 356320 5644310 70 356310 5644310 70</gml:posList>
            </gml:LinearRing></gml:interior>
          </gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
        </bldg:RoofSurface>
      </bldg:boundedBy>
      <bldg:boundedBy>
        <bldg:GroundSurface>
          <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon>
            <gml:exterior><gml:LinearRing>
              <gml:posList srsDimension="3">356300 5644300 50 356300 5644330 50 356330 5644330 50 356330 5644300 50 356300 5644300 50</gml:posList>
            </gml:LinearRing></gml:exterior>
            <gml:interior><gml:LinearRing>
              <gml:posList srsDimension="3">356310 5644310 50 356320 5644310 50 356320 5644320 50 356310 5644320 50 356310 5644310 50</gml:posList>
            </gml:LinearRing></gml:interior>
          </gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
        </bldg:GroundSurface>
      </bldg:boundedBy>
    </bldg:Building>
  </core:cityObjectMember>

  <!-- No GroundSurface: footprint from roof projection, ground from wall bottom -->
  <core:cityObjectMember>
    <bldg:Building gml:id="B_NOGROUND">
      <bldg:boundedBy>
        <bldg:WallSurface>
          <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
            <gml:posList srsDimension="3">356400 5644400 51 356406 5644400 51 356406 5644400 58 356400 5644400 58 356400 5644400 51</gml:posList>
          </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
        </bldg:WallSurface>
      </bldg:boundedBy>
      <bldg:boundedBy>
        <bldg:RoofSurface>
          <bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
            <gml:posList srsDimension="3">356400 5644400 58 356406 5644400 58 356406 5644406 58 356400 5644406 58 356400 5644400 58</gml:posList>
          </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod2MultiSurface>
        </bldg:RoofSurface>
      </bldg:boundedBy>
    </bldg:Building>
  </core:cityObjectMember>
</core:CityModel>
